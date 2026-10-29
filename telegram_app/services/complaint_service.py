
import logging
import mimetypes

import requests

from django.conf import settings
from django.utils import timezone

from ..models import Complaint, TelegramMessage
from ..ai_service import (
    analyze_complaint_text,
    validate_complaint_photo,
)

logger = logging.getLogger(__name__)

TELEGRAM_TIMEOUT = 30


def get_latest_active_complaint(conversation):
    """Return the latest complaint that still needs user input."""
    return (
        Complaint.objects.filter(
            conversation=conversation,
            status__in=[
                Complaint.Status.AWAITING_PHOTO,
                Complaint.Status.NEEDS_INFO,
            ],
        )
        .order_by("-created_at")
        .first()
    )


def send_bot_message(conversation, text):
    """Send a Telegram reply and save it in the existing chat history."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")

    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": conversation.chat_id,
                "text": text,
            },
            timeout=TELEGRAM_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            logger.error("Telegram rejected reply: %s", result)
            return False

        telegram_message = result["result"]

        saved_message = TelegramMessage.objects.create(
            conversation=conversation,
            direction=TelegramMessage.OUTGOING,
            text=text,
            telegram_message_id=telegram_message.get("message_id"),
            media_type="text",
            telegram_file_id="",
        )

        # Reuse your existing real-time dashboard broadcast.
        from ..views import broadcast_message

        broadcast_message(saved_message)
        return True

    except Exception:
        logger.exception(
            "Could not send bot reply to chat %s",
            conversation.chat_id,
        )
        return False


def download_telegram_photo(file_id):
    """Download a Telegram photo without exposing the bot token."""
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    api_response = requests.get(
        f"https://api.telegram.org/bot{token}/getFile",
        params={"file_id": file_id},
        timeout=TELEGRAM_TIMEOUT,
    )
    api_response.raise_for_status()

    result = api_response.json()

    if not result.get("ok"):
        raise RuntimeError("Telegram could not retrieve the photo")

    file_path = result["result"].get("file_path")

    if not file_path:
        raise RuntimeError("Telegram did not return a photo path")

    # Telegram file paths returned by getFile are used here.
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"

    file_response = requests.get(
        file_url,
        timeout=TELEGRAM_TIMEOUT,
    )
    file_response.raise_for_status()

    image_bytes = file_response.content

    # Protect the AI service from unexpectedly large downloads.
    if len(image_bytes) > 20 * 1024 * 1024:
        raise ValueError("The photo is too large to validate")

    mime_type = (
        file_response.headers.get("Content-Type", "").split(";")[0].strip()
        or mimetypes.guess_type(file_path)[0]
        or "image/jpeg"
    )

    if not mime_type.startswith("image/"):
        raise ValueError("The uploaded file is not an image")

    return image_bytes, mime_type


def warn_about_language(complaint, analysis):
    """Warn politely while allowing genuine complaints to continue."""
    if not analysis.get("abusive_language"):
        return

    complaint.language_warning_count += 1
    complaint.save(
        update_fields=[
            "language_warning_count",
            "updated_at",
        ]
    )

    send_bot_message(
        complaint.conversation,
        "Please keep the conversation respectful. "
        "I can still help you register your complaint.",
    )


def process_complaint_text(conversation, user_text):
    """Interpret text as a new complaint or a follow-up answer."""
    text = (user_text or "").strip()

    if not text:
        return

    active_complaint = get_latest_active_complaint(conversation)

    try:
        analysis = analyze_complaint_text(text)
    except Exception:
        logger.exception("Complaint text analysis failed")
        send_bot_message(
            conversation,
            "I'm having trouble understanding your message right now. "
            "Please try again in a moment.",
        )
        return

    # A follow-up to an existing complaint should not create a new one.
    if active_complaint:
        warn_about_language(active_complaint, analysis)

        if active_complaint.status == Complaint.Status.NEEDS_INFO:
            # This stage asks the user to provide the missing location.
            # Do not invent or infer the location.
            location = (analysis.get("location") or "").strip()

            if not location:
                # A plain-text answer may itself be a location, even when
                # it isn't a complete complaint sentence.
                location = text

            active_complaint.location = location
            active_complaint.status = Complaint.Status.PENDING_REVIEW
            active_complaint.save(
                update_fields=["location", "status", "updated_at"]
            )

            send_bot_message(
                conversation,
                "Thank you! Your complaint has been submitted for review.\n"
                f"Complaint ID: CMP-{active_complaint.complaint_id.hex[:10].upper()}\n"
                "An administrator will review the complaint and its evidence.",
            )
            return

        if active_complaint.status == Complaint.Status.AWAITING_PHOTO:
            active_complaint.additional_details = (
                f"{active_complaint.additional_details}\n{text}"
                if active_complaint.additional_details
                else text
            )
            active_complaint.save(
                update_fields=["additional_details", "updated_at"]
            )

            send_bot_message(
                conversation,
                "I've added that information to your complaint. "
                "Please send a photo showing the reported problem.",
            )
            return

    # No active complaint: determine whether this is a complaint.
    if not analysis.get("is_complaint"):
        send_bot_message(
            conversation,
            "Hello! I can help you report public problems such as "
            "damaged dustbins, overflowing waste bins, broken streetlights, "
            "or damaged roads. Please describe the problem you noticed.",
        )
        return

    description = (analysis.get("description") or text).strip()

    if not description:
        send_bot_message(
            conversation,
            "Please describe the problem so I can register your complaint.",
        )
        return

    complaint = Complaint.objects.create(
        conversation=conversation,
        category=(analysis.get("category") or "General")[:100],
        description=description,
        location=(analysis.get("location") or "")[:255],
        additional_details=analysis.get("additional_details") or "",
        status=Complaint.Status.AWAITING_PHOTO,
    )

    warn_about_language(complaint, analysis)

    send_bot_message(
        conversation,
        "I've started your complaint.\n"
        f"Complaint ID: CMP-{complaint.complaint_id.hex[:10].upper()}\n"
        f"Problem: {complaint.description}\n\n"
        "Please send a clear photo showing the reported problem. "
        "For example, if you reported a cracked dustbin, the photo "
        "should show that dustbin.",
    )


def process_complaint_photo(conversation, file_id):
    """Validate photo evidence against the active complaint."""
    complaint = get_latest_active_complaint(conversation)

    if not complaint:
        send_bot_message(
            conversation,
            "Please describe the problem first. I'll register your "
            "complaint and then ask you for photo evidence.",
        )
        return

    if complaint.status != Complaint.Status.AWAITING_PHOTO:
        send_bot_message(
            conversation,
            "I'm waiting for more information about your complaint. "
            "Please send the requested details first.",
        )
        return

    try:
        image_bytes, mime_type = download_telegram_photo(file_id)

        validation = validate_complaint_photo(
            complaint.description,
            image_bytes,
            mime_type,
        )

        result = validation["result"]
        notes = (validation.get("notes") or "").strip()

        complaint.evidence_file_id = file_id
        complaint.evidence_result = result
        complaint.evidence_notes = notes

        if result == "valid":
            if complaint.location.strip():
                complaint.status = Complaint.Status.PENDING_REVIEW
            else:
                complaint.status = Complaint.Status.NEEDS_INFO

            complaint.save(
                update_fields=[
                    "evidence_file_id",
                    "evidence_result",
                    "evidence_notes",
                    "status",
                    "updated_at",
                ]
            )

            if complaint.status == Complaint.Status.NEEDS_INFO:
                reply = (
                    "The photo appears relevant to your complaint. "
                    "Please tell me the location where the problem occurred."
                )
            else:
                reply = (
                    "Your photo appears relevant to the reported problem. "
                    "Your complaint has been submitted for administrator "
                    "review.\n"
                    f"Complaint ID: CMP-{complaint.complaint_id.hex[:10].upper()}"
                )

            if notes:
                reply += f"\nPhoto check: {notes}"

            send_bot_message(conversation, reply)

        elif result == "invalid":
            complaint.status = Complaint.Status.AWAITING_PHOTO
            complaint.save(
                update_fields=[
                    "evidence_file_id",
                    "evidence_result",
                    "evidence_notes",
                    "status",
                    "updated_at",
                ]
            )

            send_bot_message(
                conversation,
                "This photo doesn't appear to match the problem you reported. "
                "Please send a photo that clearly shows the reported issue."
                + (f"\nPhoto check: {notes}" if notes else ""),
            )

        else:  # unclear
            complaint.status = Complaint.Status.AWAITING_PHOTO
            complaint.save(
                update_fields=[
                    "evidence_file_id",
                    "evidence_result",
                    "evidence_notes",
                    "status",
                    "updated_at",
                ]
            )

            send_bot_message(
                conversation,
                "I couldn't clearly verify the problem from this photo. "
                "Please send a clearer, well-lit photo taken closer to "
                "the reported issue."
                + (f"\nPhoto check: {notes}" if notes else ""),
            )

    except Exception:
        logger.exception("Photo validation failed")

        # Do not mark an unverified photo as valid or invalid.
        complaint.evidence_result = Complaint.EvidenceResult.ERROR
        complaint.evidence_notes = (
            "Automatic validation could not be completed. "
            "The user may retry with another photo."
        )
        complaint.status = Complaint.Status.AWAITING_PHOTO
        complaint.save(
            update_fields=[
                "evidence_result",
                "evidence_notes",
                "status",
                "updated_at",
            ]
        )

        send_bot_message(
            conversation,
            "I couldn't check that photo right now. "
            "Please try again shortly with the photo.",
        )


def process_incoming_message(saved_message):
    """
    Entry point called by the existing Telegram webhook after
    it saves and broadcasts an incoming TelegramMessage.
    """
    if saved_message.direction != TelegramMessage.INCOMING:
        return

    conversation = saved_message.conversation

    if saved_message.media_type == "photo" and saved_message.telegram_file_id:
        process_complaint_photo(
            conversation,
            saved_message.telegram_file_id,
        )
        return

    if saved_message.text and saved_message.text.strip():
        process_complaint_text(
            conversation,
            saved_message.text,
        )
        return

    if saved_message.telegram_file_id:
        send_bot_message(
            conversation,
            "Please send the evidence as a photo, or describe the "
            "problem in text.",
        )
