import json
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


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

    return JsonResponse({"ok": True})

from django.shortcuts import render

from django.contrib.auth.decorators import login_required


@login_required(login_url="/accounts/login/")
def dashboard(request):
    return render(request, "telegram_app/dashboard.html")