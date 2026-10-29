
from django.contrib import admin
from .models import TelegramConversation, TelegramMessage


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
