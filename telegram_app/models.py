
from django.db import models


class TelegramConversation(models.Model):
    chat_id = models.BigIntegerField(unique=True, db_index=True)
    username = models.CharField(max_length=255, blank=True, default="")
    first_name = models.CharField(max_length=255, blank=True, default="")
    last_name = models.CharField(max_length=255, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.display_name} ({self.chat_id})"

    @property
    def display_name(self):
        if self.first_name:
            return self.first_name
        if self.username:
            return f"@{self.username}"
        return str(self.chat_id)


class TelegramMessage(models.Model):
    INCOMING = "incoming"
    OUTGOING = "outgoing"

    DIRECTION_CHOICES = [
        (INCOMING, "Incoming"),
        (OUTGOING, "Outgoing"),
    ]

    conversation = models.ForeignKey(
        TelegramConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
    )
    text = models.TextField()
    telegram_message_id = models.BigIntegerField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.direction}: {self.text[:50]}"
