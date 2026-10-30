from django.contrib import admin
from .models import Complaint

# Register your models here.

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "complaint_id",
        "category",
        "description_preview",
        "conversation",
        "location",
        "status",
        "evidence_result",
        "created_at",
    )

    list_filter = (
        "status",
        "evidence_result",
        "category",
        "created_at",
    )

    search_fields = (
        "complaint_id",
        "description",
        "location",
        "additional_details",
        "conversation__username",
        "conversation__first_name",
        "conversation__last_name",
    )

    readonly_fields = (
        "complaint_id",
        "created_at",
        "updated_at",
        "evidence_file_id",
        "evidence_result",
        "evidence_notes",
    )

    list_select_related = ("conversation",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 25

    fieldsets = (
        ("Complaint Information", {
            "fields": (
                "complaint_id",
                "conversation",
                "category",
                "description",
                "location",
                "additional_details",
                "status",
            )
        }),
        ("Photo Evidence", {
            "fields": (
                "evidence_file_id",
                "evidence_result",
                "evidence_notes",
            )
        }),
        ("Administrator Review", {
            "fields": (
                "admin_notes",
                "reviewed_by",
                "reviewed_at",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    @admin.display(description="Description")
    def description_preview(self, obj):
        description = obj.description or ""
        return (
            description[:65] + "..."
            if len(description) > 65
            else description
        )
