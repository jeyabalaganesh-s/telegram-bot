
import json
import hmac
import logging
import mimetypes
import requests
from django.conf import settings

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

import io

from PIL import Image, UnidentifiedImageError
from django.http import HttpResponse

from .models import TelegramConversation, TelegramMessage
from django.views.decorators.http import require_POST
from django.core.files.uploadedfile import UploadedFile

from .services.complaint_service import process_incoming_message    

from django.views.decorators.http import require_GET
from .models import Complaint
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .services.complaint_service import send_bot_message

logger = logging.getLogger(__name__)


# ==============================
# Helpers
# ==============================

def extract_message_content(message):
    """Extract text, caption, media type and Telegram file ID."""

    text = message.get("text") or message.get("caption") or ""
    media_type = "text"
    file_id = ""

    if message.get("photo"):
        media_type = "photo"
        # Telegram provides several sizes; use the largest available.
        file_id = message["photo"][-1]["file_id"]

    elif message.get("video"):
        media_type = "video"
        file_id = message["video"]["file_id"]

    elif message.get("animation"):
        media_type = "animation"
        file_id = message["animation"]["file_id"]

    elif message.get("document"):
        media_type = "document"
        file_id = message["document"]["file_id"]

    elif message.get("audio"):
        media_type = "audio"
        file_id = message["audio"]["file_id"]

    elif message.get("voice"):
        media_type = "voice"
        file_id = message["voice"]["file_id"]

    elif message.get("video_note"):
        media_type = "video_note"
        file_id = message["video_note"]["file_id"]

    elif message.get("sticker"):
        media_type = "sticker"
        file_id = message["sticker"]["file_id"]

    return text, media_type, file_id


def broadcast_message(saved_message):
    """Broadcast a saved message to connected WebSocket clients."""

    channel_layer = get_channel_layer()

    if channel_layer is None:
        return

    conversation = saved_message.conversation

    event_data = {
        "id": saved_message.id,
        "chat_id": conversation.chat_id,
        "username": conversation.username,
        "first_name": conversation.first_name,
        "text": saved_message.text,
        "direction": saved_message.direction,
        "media_type": saved_message.media_type,
        "created_at": saved_message.created_at.isoformat(),
    }

    if saved_message.telegram_file_id:
        event_data["media_url"] = reverse(
            "telegram_media",
            args=[saved_message.id],
        )

    try:
        async_to_sync(channel_layer.group_send)(
            "telegram_updates",
            {
                "type": "telegram_message",
                "data": event_data,
            },
        )
    except Exception:
        logger.exception(
            "Failed to broadcast message %s",
            saved_message.id,
        )


# ==============================
# Dashboard
# ==============================


@login_required(login_url="/accounts/login/")
def dashboard(request):
    total_complaints = Complaint.objects.count()

    recent_complaints = (
        Complaint.objects
        .select_related("conversation")
        .order_by("-created_at")[:10]
    )

    return render(
        request,
        "telegram_app/dashboard.html",
        {
            "total_complaints": total_complaints,
            "recent_complaints": recent_complaints,
        },
    )

# ==============================
# Telegram webhook
# ==============================

@csrf_exempt
@require_POST
def telegram_webhook(request):
    expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
    received = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )

    if not expected or not hmac.compare_digest(received, expected):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    message = update.get("message") or update.get("channel_post")

    logger.info(
        "Telegram update received. Keys: %s",
        list(message.keys()),
    )

    if not message:
        return JsonResponse({"ok": True})

    chat = message.get("chat", {})
    sender = message.get("from") or {}

    chat_id = chat.get("id")

    if chat_id is None:
        return JsonResponse({"ok": True})

    text, media_type, file_id = extract_message_content(message)

    # Ignore unsupported updates, but accept media without captions.
    if not text.strip() and not file_id:
        return JsonResponse({"ok": True})

    conversation, _ = TelegramConversation.objects.update_or_create(
        chat_id=chat_id,
        defaults={
            "username": (
                sender.get("username")
                or chat.get("username", "")
            ),
            "first_name": (
                sender.get("first_name")
                or chat.get("first_name", "")
            ),
            "last_name": (
                sender.get("last_name")
                or chat.get("last_name", "")
            ),
        },
    )

    # Avoid storing the same Telegram update twice if Telegram retries it.
    telegram_message_id = message.get("message_id")

    existing = TelegramMessage.objects.filter(
        conversation=conversation,
        telegram_message_id=telegram_message_id,
        direction=TelegramMessage.INCOMING,
    ).first()

    if existing:
        return JsonResponse({"ok": True})

    saved_message = TelegramMessage.objects.create(
        conversation=conversation,
        direction=TelegramMessage.INCOMING,
        text=text,
        telegram_message_id=telegram_message_id,
        media_type=media_type,
        telegram_file_id=file_id,
    )
    broadcast_message(saved_message)

    logger.info(
        "Saved incoming %s message for chat %s",
        media_type,
        chat_id,
    )

    try:
        process_incoming_message(saved_message)
    except Exception:
        logger.exception(
            "Complaint processing failed for chat %s",
            chat_id,
        )

    return JsonResponse({"ok": True})


# ==============================
# Serve media securely
# ==============================

@login_required(login_url="/")
def telegram_media(request, message_id):
    """Retrieve a Telegram file without exposing the bot token to the browser."""

    saved_message = get_object_or_404(
        TelegramMessage.objects.select_related("conversation"),
        pk=message_id,
    )

    file_id = saved_message.telegram_file_id

    if not file_id:
        return JsonResponse(
            {"error": "This message has no media file."},
            status=404,
        )

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")

    if not token:
        return JsonResponse(
            {"error": "Telegram bot token is not configured."},
            status=500,
        )

    try:
        # Ask Telegram for the file path.
        api_response = requests.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": file_id},
            timeout=15,
        )
        api_response.raise_for_status()
        api_result = api_response.json()

        if not api_result.get("ok"):
            return JsonResponse(
                {"error": "Telegram could not retrieve this file."},
                status=502,
            )

        file_path = api_result["result"]["file_path"]

        # Download through the backend; don't expose the bot token to JS.
        download_url = (
            f"https://api.telegram.org/file/bot{token}/{file_path}"
        )

        file_response = requests.get(
            download_url,
            timeout=30,
        )
        file_response.raise_for_status()

        content_type = file_response.headers.get("Content-Type")

        if not content_type or content_type == "application/octet-stream":
            content_type = mimetypes.guess_type(file_path)[0]

        if not content_type:
            content_type = "application/octet-stream"

        response = HttpResponse(
            file_response.content,
            content_type=content_type,
        )
        response["Content-Disposition"] = "inline"
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"

        return response

    except (requests.RequestException, ValueError, KeyError):
        logger.exception(
            "Failed to retrieve Telegram media for message %s",
            message_id,
        )
        return JsonResponse(
            {"error": "Could not retrieve media from Telegram."},
            status=502,
        )


# ==============================
# Conversation list
# ==============================

@login_required(login_url="/")
def conversations(request):
    items = TelegramConversation.objects.prefetch_related(
        "messages"
    ).all()

    return render(
        request,
        "telegram_app/conversations.html",
        {"conversations": items},
    )


# ==============================
# Individual chat
# ==============================


@login_required(login_url="/")
def telegram_chat(request, chat_id):
    conversation = get_object_or_404(
        TelegramConversation,
        chat_id=chat_id,
    )

    messages = conversation.messages.all()

    conversations = TelegramConversation.objects.prefetch_related(
        "messages"
    ).all()

    return render(
        request,
        "telegram_app/chat.html",
        {
            "conversation": conversation,
            "messages": messages,
            "conversations": conversations,
        },
    )



# ==============================
# Send Telegram text message
# ==============================

@login_required(login_url="/")
@require_POST
def send_telegram_message(request, chat_id):
    conversation = get_object_or_404(
        TelegramConversation,
        chat_id=chat_id,
    )

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"ok": False, "error": "Invalid request data."},
            status=400,
        )

    text = data.get("text", "")

    if not isinstance(text, str):
        return JsonResponse(
            {"ok": False, "error": "Message must be text."},
            status=400,
        )

    text = text.strip()

    if not text or len(text) > 4096:
        return JsonResponse(
            {
                "ok": False,
                "error": "Enter a message of 1–4096 characters.",
            },
            status=400,
        )

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")

    if not token:
        return JsonResponse(
            {
                "ok": False,
                "error": "Telegram bot token is not configured.",
            },
            status=500,
        )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": conversation.chat_id,
                "text": text,
            },
            timeout=15,
        )
        result = response.json()

    except (requests.RequestException, ValueError):
        logger.exception("Telegram sendMessage request failed")
        return JsonResponse(
            {"ok": False, "error": "Could not contact Telegram."},
            status=502,
        )

    if not response.ok or not result.get("ok"):
        return JsonResponse(
            {
                "ok": False,
                "error": result.get(
                    "description",
                    "Telegram rejected the message.",
                ),
            },
            status=502,
        )

    sent_message = result["result"]

    saved_message = TelegramMessage.objects.create(
        conversation=conversation,
        direction=TelegramMessage.OUTGOING,
        text=text,
        telegram_message_id=sent_message.get("message_id"),
        media_type="text",
        telegram_file_id="",
    )

    broadcast_message(saved_message)

    return JsonResponse({
        "ok": True,
        "message": {
            "id": saved_message.id,
            "chat_id": conversation.chat_id,
            "text": saved_message.text,
            "direction": saved_message.direction,
            "media_type": saved_message.media_type,
            "created_at": saved_message.created_at.isoformat(),
        },
    })


@csrf_exempt
@login_required(login_url="/")
@require_POST
def send_telegram_media(request, chat_id):
    """Upload media from JEMI and send it to a Telegram chat."""

    conversation = get_object_or_404(
        TelegramConversation,
        chat_id=chat_id,
    )

    uploaded_file = request.FILES.get("file")
    caption = request.POST.get("caption", "").strip()

    if not uploaded_file:
        return JsonResponse(
            {"ok": False, "error": "Please select a file."},
            status=400,
        )

    # Keep uploads within a reasonable size for the dashboard.
    max_size = 20 * 1024 * 1024  # 20 MB
    if uploaded_file.size > max_size:
        return JsonResponse(
            {"ok": False, "error": "File size must not exceed 20 MB."},
            status=400,
        )

    if len(caption) > 1024:
        return JsonResponse(
            {"ok": False, "error": "Caption must be 1024 characters or fewer."},
            status=400,
        )

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token:
        return JsonResponse(
            {"ok": False, "error": "Telegram bot token is not configured."},
            status=500,
        )

    content_type = (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    ).lower()

    # Select the Telegram Bot API method.
    if content_type.startswith("image/"):
        media_type = "photo"
        api_method = "sendPhoto"
        file_field = "photo"
    elif content_type.startswith("video/"):
        media_type = "video"
        api_method = "sendVideo"
        file_field = "video"
    elif content_type.startswith("audio/"):
        media_type = "audio"
        api_method = "sendAudio"
        file_field = "audio"
    else:
        media_type = "document"
        api_method = "sendDocument"
        file_field = "document"

    api_url = f"https://api.telegram.org/bot{token}/{api_method}"

    try:
        uploaded_file.seek(0)

        response = requests.post(
            api_url,
            data={
                "chat_id": conversation.chat_id,
                "caption": caption,
            },
            files={
                file_field: (
                    uploaded_file.name,
                    uploaded_file,
                    content_type,
                )
            },
            timeout=60,
        )

        result = response.json()

    except (requests.RequestException, ValueError):
        logger.exception("Telegram media upload failed")
        return JsonResponse(
            {"ok": False, "error": "Could not upload media to Telegram."},
            status=502,
        )

    if not response.ok or not result.get("ok"):
        return JsonResponse(
            {
                "ok": False,
                "error": result.get(
                    "description",
                    "Telegram rejected the media.",
                ),
            },
            status=502,
        )

    telegram_message = result["result"]

    # Telegram returns the file_id for the uploaded media.
    returned_file_id = ""
    returned_media_type = media_type

    media_object = telegram_message.get(file_field)

    if media_type == "photo":
        photos = telegram_message.get("photo", [])
        if photos:
            returned_file_id = photos[-1]["file_id"]
    elif isinstance(media_object, dict):
        returned_file_id = media_object.get("file_id", "")

    # Save the actual Telegram message ID, not the local database ID.
    saved_message = TelegramMessage.objects.create(
        conversation=conversation,
        direction=TelegramMessage.OUTGOING,
        text=telegram_message.get("caption") or caption,
        telegram_message_id=telegram_message.get("message_id"),
        media_type=returned_media_type,
        telegram_file_id=returned_file_id,
    )

    broadcast_message(saved_message)

    return JsonResponse({
        "ok": True,
        "message": {
            "id": saved_message.id,
            "chat_id": conversation.chat_id,
            "text": saved_message.text,
            "direction": saved_message.direction,
            "media_type": saved_message.media_type,
            "media_url": (
                reverse("telegram_media", args=[saved_message.id])
                if returned_file_id else None
            ),
            "created_at": saved_message.created_at.isoformat(),
        },
    })



def broadcast_telegram_message(message):
    conversation = message.conversation

    payload = {
        "id": message.id,
        "chat_id": conversation.chat_id,
        "display_name": conversation.display_name,
        "username": conversation.username,
        "direction": message.direction,
        "text": message.text or "",
        "media_type": message.media_type,
        "created_at": message.created_at.isoformat(),
    }

    channel_layer = get_channel_layer()

    if channel_layer is not None:
        async_to_sync(channel_layer.group_send)(
            "telegram_updates",
            {
                "type": "telegram.message",
                "data": payload,
            },
        )


@login_required
@require_GET
def dashboard_messages_api(request):
    # Fetch saved incoming Telegram messages.
    messages = (
        TelegramMessage.objects
        .filter(direction=TelegramMessage.INCOMING)
        .select_related("conversation")
        .order_by("-created_at")
    )

    # Total number saved in the database.
    total_count = messages.count()

    # Return the most recent 100 messages.
    recent_messages = messages[:100]

    data = []

    for message in recent_messages:
        conversation = message.conversation

        data.append({
            "id": message.id,
            "chat_id": conversation.chat_id,
            "display_name": conversation.display_name,
            "username": conversation.username,
            "direction": message.direction,
            "text": message.text or "",
            "media_type": message.media_type,
            "created_at": message.created_at.isoformat(),
        })

    return JsonResponse({
        "success": True,
        "total_count": total_count,
        "messages": data,
    })


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
        "telegram_app/complaints.html",
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
        "telegram_app/complaint_detail.html",
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