
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from telegram_app.views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),

    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),

    path("", dashboard, name="dashboard"),
    path("telegram/", include("telegram_app.urls")),

    path("complaints/", include("complaints.urls")),
]
