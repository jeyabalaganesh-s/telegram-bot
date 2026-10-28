from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("webhook/", views.telegram_webhook, name="telegram_webhook"),
    path("messages/", views.conversations, name="conversations"),
    path(
        "messages/<int:chat_id>/",
        views.telegram_chat,
        name="telegram_chat",
    ),
    path(
        "messages/<int:chat_id>/send/",
        views.send_telegram_message,
        name="send_telegram_message",
    ),
]