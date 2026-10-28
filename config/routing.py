from django.urls import path
from telegram_app.consumers import TelegramConsumer

websocket_urlpatterns = [
    path("ws/telegram/", TelegramConsumer.as_asgi()),
]