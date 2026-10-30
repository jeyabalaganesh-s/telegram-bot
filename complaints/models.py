from django.db import models

import uuid

from django.conf import settings

# Create your models here.
class Complaint(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING_PHOTO = "awaiting_photo", "Awaiting Photo"
        NEEDS_INFO = "needs_info", "Needs More Information"
        PENDING_REVIEW = "pending_review", "Pending Admin Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CLOSED = "closed", "Closed"

    class EvidenceResult(models.TextChoices):
        NOT_CHECKED = "not_checked", "Not Checked"
        VALID = "valid", "Relevant Photo"
        INVALID = "invalid", "Unrelated Photo"
        UNCLEAR = "unclear", "Unclear Photo"
        ERROR = "error", "Validation Error"

    complaint_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    conversation = models.ForeignKey(
        "telegram_app.TelegramConversation",
        on_delete=models.CASCADE,
        related_name="complaints",
    )

    category = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    location = models.CharField(max_length=255, blank=True)
    additional_details = models.TextField(blank=True)

    # Store Telegram's file ID, not the bot token or a public URL.
    evidence_file_id = models.CharField(
        max_length=512,
        blank=True,
    )
    evidence_result = models.CharField(
        max_length=20,
        choices=EvidenceResult.choices,
        default=EvidenceResult.NOT_CHECKED,
    )
    evidence_notes = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    language_warning_count = models.PositiveIntegerField(default=0)

    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_complaints",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CMP-{self.complaint_id.hex[:10].upper()}"
