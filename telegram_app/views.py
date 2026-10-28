
import json
import hmac
import logging
import requests

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import TelegramConversation, TelegramMessage


logger = logging.getLogger(__name__)


# ==============================
# Dashboard
# ==============================

@login_required(login_url="/accounts/login/")
def dashboard(request):
    return render(request, "telegram_app/dashboard.html")


# ==============================
# Telegram webhook
# ==============================

@csrf_exempt
@require_POST
def telegram_webhook(request):
    expected = settings.TELEGRAM_WEBHOOK_SECRET or ""
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

    # Some Telegram updates do not contain a message.
    if not message:
        return JsonResponse({"ok": True})

    chat = message.get("chat", {})
    sender = message.get("from", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    # This version stores text messages only.
    if chat_id is None or not isinstance(text, str) or not text.strip():
        return JsonResponse({"ok": True})

    # Save the conversation and message before broadcasting.
    conversation, _ = TelegramConversation.objects.update_or_create(
        chat_id=chat_id,
        defaults={
            "username": sender.get("username") or chat.get("username", ""),
            "first_name": sender.get("first_name") or chat.get("first_name", ""),
            "last_name": sender.get("last_name") or chat.get("last_name", ""),
        },
    )

    saved_message = TelegramMessage.objects.create(
        conversation=conversation,
        direction=TelegramMessage.INCOMING,
        text=text,
        telegram_message_id=message.get("message_id"),
    )

    # Broadcast the saved message to connected WebSocket clients.
    channel_layer = get_channel_layer()

    if channel_layer is not None:
        event_data = {
            "id": saved_message.id,
            "chat_id": chat_id,
            "username": conversation.username,
            "first_name": conversation.first_name,
            "text": saved_message.text,
            "direction": TelegramMessage.INCOMING,
            "created_at": saved_message.created_at.isoformat(),
        }

        try:
            async_to_sync(channel_layer.group_send)(
                "telegram_updates",
                {
                    "type": "telegram_message",
                    "data": event_data,
                },
            )
        except Exception:
            # The message is already saved, even if live delivery fails.
            logger.exception("Failed to broadcast Telegram message")

    logger.info("Saved incoming Telegram message for chat %s", chat_id)

    return JsonResponse({"ok": True})


# ==============================
# Conversation list
# ==============================

@login_required(login_url="/accounts/login/")
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

@login_required(login_url="/accounts/login/")
def telegram_chat(request, chat_id):
    conversation = get_object_or_404(
        TelegramConversation,
        chat_id=chat_id,
    )

    messages = conversation.messages.all()

    return render(
        request,
        "telegram_app/chat.html",
        {
            "conversation": conversation,
            "messages": messages,
        },
    )


# ==============================
# Send Telegram message
# ==============================

@login_required(login_url="/accounts/login/")
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
            {"ok": False, "error": "Enter a message of 1–4096 characters."},
            status=400,
        )

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")

    if not token:
        return JsonResponse(
            {"ok": False, "error": "Telegram bot token is not configured."},
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
    )

    # Broadcast outgoing messages too, so other open pages can update.
    channel_layer = get_channel_layer()

    if channel_layer is not None:
        try:
            async_to_sync(channel_layer.group_send)(
                "telegram_updates",
                {
                    "type": "telegram_message",
                    "data": {
                        "id": saved_message.id,
                        "chat_id": conversation.chat_id,
                        "username": conversation.username,
                        "first_name": conversation.first_name,
                        "text": saved_message.text,
                        "direction": TelegramMessage.OUTGOING,
                        "created_at": saved_message.created_at.isoformat(),
                    },
                },
            )
        except Exception:
            logger.exception("Failed to broadcast outgoing message")

    return JsonResponse({
        "ok": True,
        "message": {
            "id": saved_message.id,
            "chat_id": conversation.chat_id,
            "text": saved_message.text,
            "direction": saved_message.direction,
            "created_at": saved_message.created_at.isoformat(),
        },
    })
