import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Request(TimeStampedModel):
    """A visitor submission: guided discovery, consultation request or contact message.

    `id` is the browser-generated idempotency key (`requestKey`), so safe retries return
    the same record. `uuid` (from TimeStampedModel) is kept for consistency with other models.
    """

    class Kind(models.TextChoices):
        DISCOVERY = "discovery", "Discovery"
        CONSULTATION = "consultation", "Consultation"
        CONTACT = "contact", "Contact"

    class Audience(models.TextChoices):
        BUSINESS = "business", "Business"
        GOVERNMENT = "government", "Government"
        AGENCY = "agency", "Agency"
        INDIVIDUAL = "individual", "Individual"

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        IN_REVIEW = "in_review", "In review"
        NEEDS_INFORMATION = "needs_information", "Needs information"
        PROPOSAL_PREPARING = "proposal_preparing", "Proposal preparing"
        PROPOSAL_SENT = "proposal_sent", "Proposal sent"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        DECLINED = "declined", "Declined"
        CANCELED = "canceled", "Canceled"

    class QuoteStatus(models.TextChoices):
        NONE = "none", "No quote yet"
        SENT = "sent", "Quote sent"
        ACCEPTED = "accepted", "Quote accepted"
        LOST = "lost", "Quote lost"

    class ValueRange(models.TextChoices):
        # Placeholder bands (EGP); the labels can be changed later without a data change.
        UNDER_50K = "lt_50k", "Under 50k EGP"
        FROM_50K_TO_200K = "50k_200k", "50k to 200k EGP"
        OVER_200K = "gt_200k", "Over 200k EGP"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=24, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    audience = models.CharField(max_length=20, choices=Audience.choices, db_index=True)
    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254, db_index=True)
    organization = models.CharField(max_length=200)
    language = models.CharField(max_length=2, default="en")
    details = models.JSONField(default=dict)
    consent = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING_REVIEW, db_index=True)
    internal_note = models.TextField(blank=True, default="", max_length=3000)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="requests"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_requests"
    )
    # Lead pipeline (FL-15). Team-only: none of these is ever shown to the customer.
    source_page = models.CharField(
        "Source page", max_length=255, blank=True, default="", help_text="Page the visitor came from, if sent."
    )
    utm_source = models.CharField("UTM source", max_length=100, blank=True, default="", db_index=True)
    utm_medium = models.CharField("UTM medium", max_length=100, blank=True, default="")
    utm_campaign = models.CharField("UTM campaign", max_length=100, blank=True, default="")
    next_follow_up = models.DateField(
        "Next follow-up", null=True, blank=True, db_index=True, help_text="The day the team should reply or call next."
    )
    quote_status = models.CharField(
        "Quote", max_length=10, choices=QuoteStatus.choices, default=QuoteStatus.NONE, db_index=True
    )
    value_range = models.CharField(
        "Value range", max_length=10, choices=ValueRange.choices, blank=True, default="", db_index=True
    )
    first_reply_at = models.DateTimeField(
        "First reply", null=True, blank=True, help_text="Set once, at the first staff status change or note."
    )

    class Meta:
        db_table = "leads_request"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"], name="leads_req_status_created_idx")]

    def __str__(self):
        return f"{self.reference} · {self.name}"


class Appointment(TimeStampedModel):
    class Status(models.TextChoices):
        PROVISIONAL = "provisional", "Provisional"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELED = "canceled", "Canceled"

    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="appointments")
    slot = models.CharField(max_length=16)  # "YYYY-MM-DDTHH:MM" (Africa/Cairo local time)
    date = models.DateField(db_index=True)
    time = models.CharField(max_length=5)
    timezone = models.CharField(max_length=40, default="Africa/Cairo")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROVISIONAL, db_index=True)

    class Meta:
        db_table = "leads_appointment"
        ordering = ["-id"]
        constraints = [
            # Only one active (provisional/confirmed) booking per slot; canceled slots free up.
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(status__in=["provisional", "confirmed"]),
                name="appointments_active_slot_unique",
            )
        ]

    def __str__(self):
        return f"{self.slot} ({self.status})"


class RequestEvent(TimeStampedModel):
    """Append-only history of what happened to a request."""

    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=40, db_index=True)  # submitted | status_changed | note_updated | ...
    status = models.CharField(max_length=30, blank=True, null=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="request_events"
    )

    class Meta:
        db_table = "leads_request_event"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["request", "created_at"], name="leads_event_req_created_idx")]

    def __str__(self):
        return f"{self.event_type}:{self.status}"


class AssistantMessage(TimeStampedModel):
    """Optional log of assistant exchanges (only written when ASSISTANT_LOG_ENABLED=True)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assistant_messages"
    )
    language = models.CharField(max_length=2)
    message = models.TextField(max_length=2000)
    reply = models.TextField(max_length=6000)
    mode = models.CharField(max_length=10)

    class Meta:
        db_table = "leads_assistant_message"
        ordering = ["-created_at"]

    def __str__(self):
        return self.message[:60]


# Module-level aliases used by drf-spectacular ENUM_NAME_OVERRIDES.
RequestStatus = Request.Status
AppointmentStatus = Appointment.Status
