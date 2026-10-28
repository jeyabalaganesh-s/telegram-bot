import json
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import TelegramConversation, TelegramMessage


@csrf_exempt
@require_POST
def telegram_webhook(request):
    expected = settings.TELEGRAM_WEBHOOK_SECRET or ""
    received = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token", ""
    )

    if not expected or not hmac.compare_digest(
        received, expected
    ):
        return JsonResponse(
            {"error": "Unauthorized"},
            status=403,
        )

    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400,
        )

    message = update.get("message") or update.get("channel_post")

    if message:
        sender = message.get("from", {})
        chat = message.get("chat", {})

        data = {
            "chat_id": chat.get("id"),
            "username": sender.get("username"),
            "text": message.get("text", ""),
            "date": message.get("date"),
        }

        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            "telegram_updates",
            {
                "type": "telegram_message",
                "data": data,
            },
        )

        print("Received Telegram message:", data)

            
    # `message` is the incoming Telegram message dictionary.
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if chat_id is not None and isinstance(text, str) and text.strip():
        conversation, _ = TelegramConversation.objects.update_or_create(
            chat_id=chat_id,
            defaults={
                "username": chat.get("username", ""),
                "first_name": chat.get("first_name", ""),
                "last_name": chat.get("last_name", ""),
            },
        )

        saved_message = TelegramMessage.objects.create(
            conversation=conversation,
            direction=TelegramMessage.INCOMING,
            text=text,
            telegram_message_id=message.get("message_id"),
        )

        # Keep your existing Channels broadcast logic here.


    return JsonResponse({"ok": True})

from django.shortcuts import render

from django.contrib.auth.decorators import login_required


@login_required(login_url="/accounts/login/")
def dashboard(request):
    return render(request, "telegram_app/dashboard.html")



import json
import requests

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from .models import TelegramConversation, TelegramMessage


@login_required
def conversations(request):
    items = TelegramConversation.objects.prefetch_related(
        "messages"
    ).all()

    return render(
        request,
        "telegram_app/conversations.html",
        {"conversations": items},
    )


@login_required
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


@login_required
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
        return JsonResponse(
            {"ok": False, "error": "Could not contact Telegram."},
            status=502,
        )

    if not response.ok or not result.get("ok"):
        return JsonResponse(
            {
                "ok": False,
                "error": result.get("description", "Telegram rejected the message."),
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

    return JsonResponse({
        "ok": True,
        "message": {
            "id": saved_message.id,
            "text": saved_message.text,
            "direction": saved_message.direction,
            "created_at": saved_message.created_at.isoformat(),
        },
    })
