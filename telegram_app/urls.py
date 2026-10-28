from django.urls import path
from .views import telegram_webhook, dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("webhook/", telegram_webhook, name="telegram_webhook"),
]