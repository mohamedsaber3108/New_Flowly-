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


def default_booking_weekdays():
    """Sunday to Thursday, as Python weekday numbers (Monday=0 ... Sunday=6): today's behaviour."""
    return [0, 1, 2, 3, 6]


def default_slot_times():
    return ["10:00", "11:00", "12:00", "14:00", "15:00"]


class SiteSettings(models.Model):
    """The one row of settings the team changes in the admin (FL-21). Secrets are NOT stored here: they stay in env.

    The defaults reproduce the behaviour before this model existed. Read it through `apps.leads.site_settings.get()`
    (cached for 60 seconds, cleared on save).
    """

    assistant_enabled = models.BooleanField(
        "Assistant on", default=True, help_text="Off: the chat assistant answers with a short 'switched off' message."
    )
    intake_enabled = models.BooleanField(
        "New requests on",
        default=True,
        help_text=(
            "Off: the public forms show a clear message and save nothing. " "Requests already received are not touched."
        ),
    )
    booking_weekdays = models.JSONField(
        "Booking days",
        default=default_booking_weekdays,
        help_text="Days of the week when consultations can be requested.",
    )
    slot_times = models.JSONField(
        "Time slots (Africa/Cairo)", default=default_slot_times, help_text="24-hour times, for example 10:00."
    )
    booking_horizon_days = models.PositiveSmallIntegerField(
        "How far ahead (days)", default=90, help_text="A date must be after today and at most this many days away."
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        db_table = "leads_site_settings"
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # a singleton: there is only ever one row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BlockedDay(models.Model):
    """A date (holiday, team away) on which no consultation can be requested."""

    date = models.DateField(unique=True, db_index=True)
    reason = models.CharField(max_length=200, blank=True, help_text="For the team only; it is never shown to visitors.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "leads_blocked_day"
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} {self.reason}".strip()


# Module-level aliases used by drf-spectacular ENUM_NAME_OVERRIDES.
RequestStatus = Request.Status
AppointmentStatus = Appointment.Status
