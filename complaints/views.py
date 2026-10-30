from django.shortcuts import render

import logging
import requests
from django.conf import settings


from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404

import io

from PIL import Image, UnidentifiedImageError
from django.http import HttpResponse


from django.views.decorators.http import require_GET
from .models import Complaint
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .services.complaint_service import send_bot_message

logger = logging.getLogger(__name__)

# Create your views here.


@login_required
def complaints_dashboard(request):
    """Display complaints in the authenticated JEMI application."""

    complaints = (
        Complaint.objects
        .select_related("conversation", "reviewed_by")
        .order_by("-created_at")
    )

    # Filter by complaint status.
    selected_status = request.GET.get("status", "").strip()
    valid_statuses = {
        value for value, label in Complaint.Status.choices
    }

    if selected_status in valid_statuses:
        complaints = complaints.filter(status=selected_status)
    else:
        selected_status = ""

    # Search complaint details and Telegram user information.
    search_query = request.GET.get("q", "").strip()

    if search_query:
        complaints = complaints.filter(
            Q(description__icontains=search_query)
            | Q(category__icontains=search_query)
            | Q(location__icontains=search_query)
            | Q(additional_details__icontains=search_query)
            | Q(conversation__username__icontains=search_query)
            | Q(conversation__first_name__icontains=search_query)
            | Q(conversation__last_name__icontains=search_query)
        )

    context = {
        "complaints": complaints,
        "search_query": search_query,
        "selected_status": selected_status,
        "status_choices": Complaint.Status.choices,
        "total_complaints": Complaint.objects.count(),
        "pending_complaints": Complaint.objects.filter(
            status=Complaint.Status.PENDING_REVIEW
        ).count(),
        "awaiting_photo": Complaint.objects.filter(
            status=Complaint.Status.AWAITING_PHOTO
        ).count(),
        "approved_complaints": Complaint.objects.filter(
            status=Complaint.Status.APPROVED
        ).count(),
    }

    return render(
        request,
        "complaints/complaints.html",
        context,
    )


@login_required
@require_http_methods(["GET", "POST"])
def complaint_detail(request, complaint_id):
    """View evidence and update a complaint's status."""

    complaint = get_object_or_404(
        Complaint.objects.select_related("conversation", "reviewed_by"),
        complaint_id=complaint_id,
    )

    if request.method == "POST":
        new_status = request.POST.get("status", "").strip()
        admin_notes = request.POST.get("admin_notes", "").strip()

        valid_statuses = {
            value for value, label in Complaint.Status.choices
        }

        if new_status not in valid_statuses:
            messages.error(request, "Please select a valid complaint status.")
            return redirect(
                "complaint_detail",
                complaint_id=complaint.complaint_id,
            )

        previous_status = complaint.status
        complaint.status = new_status
        complaint.admin_notes = admin_notes

        if new_status in {
            Complaint.Status.APPROVED,
            Complaint.Status.REJECTED,
            Complaint.Status.CLOSED,
        }:
            complaint.reviewed_by = request.user
            from django.utils import timezone
            complaint.reviewed_at = timezone.now()

        complaint.save(
            update_fields=[
                "status",
                "admin_notes",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        # Notify the complainant when the complaint is resolved/closed.
        if (
            new_status == Complaint.Status.CLOSED
            and previous_status != Complaint.Status.CLOSED
        ):
            complaint_code = (
                f"CMP-{complaint.complaint_id.hex[:10].upper()}"
            )

            notification = (
                f"Your complaint {complaint_code} has been marked as "
                "resolved by the administrator. Thank you for reporting "
                "this issue."
            )

            if admin_notes:
                notification += f"\nAdministrator note: {admin_notes}"

            sent = send_bot_message(complaint.conversation, notification)

            if sent:
                messages.success(
                    request,
                    "Complaint updated and resolution notification sent "
                    "through Telegram.",
                )
            else:
                messages.warning(
                    request,
                    "Complaint updated, but the Telegram notification "
                    "could not be sent. Check your server logs.",
                )
        else:
            messages.success(request, "Complaint updated successfully.")

        return redirect(
            "complaint_detail",
            complaint_id=complaint.complaint_id,
        )

    return render(
        request,
        "complaints/complaint_detail.html",
        {
            "complaint": complaint,
            "status_choices": Complaint.Status.choices,
        },
    )


@login_required
def complaint_evidence(request, complaint_id):
    """Serve verified complaint image evidence to logged-in users."""

    complaint = get_object_or_404(
        Complaint,
        complaint_id=complaint_id,
    )

    if not complaint.evidence_file_id:
        return HttpResponse("No photo evidence available.", status=404)

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        return HttpResponse(
            "Telegram bot is not configured.",
            status=503,
        )

    try:
        file_info_response = requests.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": complaint.evidence_file_id},
            timeout=20,
        )
        file_info_response.raise_for_status()
        file_info = file_info_response.json()

        if not file_info.get("ok"):
            return HttpResponse(
                "Could not retrieve photo evidence.",
                status=502,
            )

        file_path = file_info.get("result", {}).get("file_path")
        if not file_path:
            return HttpResponse(
                "Photo path unavailable.",
                status=404,
            )

        photo_response = requests.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}",
            timeout=30,
        )
        photo_response.raise_for_status()
        image_bytes = photo_response.content

        if not image_bytes:
            return HttpResponse("Empty image file.", status=404)

        if len(image_bytes) > 20 * 1024 * 1024:
            return HttpResponse("Image is too large.", status=413)

        # Verify the actual image rather than trusting the HTTP header.
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image_format = image.format
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError):
            logger.warning(
                "Invalid evidence image for complaint %s",
                complaint_id,
            )
            return HttpResponse(
                "The evidence file is not a valid image.",
                status=415,
            )

        content_types = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
            "GIF": "image/gif",
        }

        content_type = content_types.get(image_format)
        if not content_type:
            return HttpResponse(
                "Unsupported image format.",
                status=415,
            )

        response = HttpResponse(
            image_bytes,
            content_type=content_type,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline"
        return response

    except requests.RequestException:
        logger.exception(
            "Could not retrieve evidence for complaint %s",
            complaint_id,
        )
        return HttpResponse(
            "Unable to retrieve photo evidence.",
            status=502,
        )

    
@login_required(login_url="/accounts/login/")
@require_GET
def dashboard_complaints_count(request):
    return JsonResponse({
        "total_complaints": Complaint.objects.count(),
    })