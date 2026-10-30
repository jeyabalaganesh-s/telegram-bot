from django.urls import path
from . import views

urlpatterns = [
    path(
        "",
        views.complaints_dashboard,
        name="complaints_dashboard",
    ),

    path(
        "<uuid:complaint_id>/",
        views.complaint_detail,
        name="complaint_detail",
    ),

    path(
        "<uuid:complaint_id>/evidence/",
        views.complaint_evidence,
        name="complaint_evidence",
    ),

    path(
        "api/count/",
        views.dashboard_complaints_count,
        name="dashboard_complaints_count",
    ),
]