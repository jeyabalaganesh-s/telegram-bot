
from django.contrib import admin
from .models import TelegramConversation, TelegramMessage, Complaint

class TelegramMessageInline(admin.TabularInline):
    model = TelegramMessage
    extra = 0
    readonly_fields = (
        "telegram_message_id",
        "created_at",
    )
    fields = (
        "direction",
        "text",
        "media_type",
        "telegram_file_id",
        "telegram_message_id",
        "created_at",
    )
    ordering = ("created_at",)


@admin.register(TelegramConversation)
class TelegramConversationAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "chat_id",
        "username",
        "first_name",
        "updated_at",
    )

    search_fields = (
        "username",
        "first_name",
        "last_name",
        "chat_id",
    )

    list_filter = ("updated_at",)
    readonly_fields = ("updated_at",)
    ordering = ("-updated_at",)
    inlines = [TelegramMessageInline]


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "direction",
        "media_type",
        "telegram_message_id",
        "created_at",
    )

    search_fields = (
        "text",
        "conversation__username",
        "conversation__first_name",
        "telegram_message_id",
        "telegram_file_id",
    )

    list_filter = (
        "direction",
        "media_type",
        "created_at",
    )

    readonly_fields = ("created_at",)
    list_select_related = ("conversation",)
    ordering = ("-created_at",)

    fieldsets = (
        ("Message Details", {
            "fields": (
                "conversation",
                "direction",
                "text",
                "created_at",
            ),
        }),
        ("Telegram Media", {
            "fields": (
                "media_type",
                "telegram_file_id",
                "telegram_message_id",
            ),
        }),
    )




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
