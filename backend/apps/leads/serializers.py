import re
from datetime import date as date_cls

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.utils import iso

from . import site_settings
from .models import Appointment, Request, RequestEvent

REFERENCE_RE = re.compile(r"^FLW-\d{8}-[A-F0-9]{8}$")


def _opt(max_length=300):
    return serializers.CharField(
        max_length=max_length, required=False, allow_blank=True, default="", trim_whitespace=True
    )


class RequestCreateSerializer(serializers.Serializer):
    """Mirrors the frontend Zod schema (lib/api.ts) field for field."""

    requestKey = serializers.UUIDField()
    name = serializers.CharField(min_length=2, max_length=150)
    email = serializers.EmailField(max_length=254)
    organization = serializers.CharField(min_length=2, max_length=200)
    kind = serializers.ChoiceField(choices=Request.Kind.choices)
    audience = serializers.ChoiceField(choices=Request.Audience.choices)
    requirements = serializers.CharField(min_length=20, max_length=5000)
    role = _opt()
    phone = _opt()
    website = _opt()
    industry = _opt()
    size = _opt()
    tools = _opt()
    timeline = _opt()
    budget = _opt()
    hosting = _opt()
    department = _opt()
    classification = _opt()
    reference = _opt()
    subject = _opt()
    goals = serializers.ListField(
        child=serializers.CharField(max_length=30), max_length=10, required=False, default=list
    )
    recommended = serializers.ListField(
        child=serializers.CharField(max_length=100), max_length=4, required=False, default=list
    )
    selectedService = _opt()
    # Where the visitor came from (FL-15). Optional; kept for the team only.
    sourcePage = _opt(255)
    utmSource = _opt(100)  # lower-cased; anything but a-z 0-9 _ . - is saved as "other" (see validate_utmSource)
    utmMedium = _opt(100)
    utmCampaign = _opt(100)
    consent = serializers.BooleanField()
    date = serializers.RegexField(r"^\d{4}-\d{2}-\d{2}$", allow_null=True, required=False, default=None)
    time = serializers.CharField(allow_null=True, required=False, default=None, max_length=5)
    timezone = serializers.ChoiceField(choices=["Africa/Cairo"])
    language = serializers.ChoiceField(choices=["ar", "en"])

    def validate_time(self, value):
        """One of the time slots set in the site settings (default 10:00, 11:00, 12:00, 14:00, 15:00)."""
        if value is not None and value not in site_settings.get().slot_times:
            raise serializers.ValidationError(f'"{value}" is not a valid choice.')
        return value

    def validate_utmSource(self, value):
        from .pipeline import clean_source

        return clean_source(value)

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("Please agree to the use of your information for this request.")
        return value

    def validate(self, attrs):
        if attrs["audience"] == "government" and not attrs["department"].strip():
            raise serializers.ValidationError({"department": "Department / institution type is required"})
        if bool(attrs.get("date")) != bool(attrs.get("time")):
            raise serializers.ValidationError({"date": "Choose both date and time"})
        if attrs["kind"] == "consultation" and not attrs.get("date"):
            raise serializers.ValidationError({"date": "Consultation date is required"})
        return attrs


class RequestLookupSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=40)
    email = serializers.EmailField(max_length=254)

    def validate_reference(self, value):
        value = value.strip().upper()
        if not REFERENCE_RE.match(value):
            raise serializers.ValidationError("Enter your reference and email.")
        return value

    def validate_email(self, value):
        return value.strip().lower()


class RequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Request.Status.choices)
    internalNote = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")


class AssistantHistoryItem(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField(max_length=4000, allow_blank=True)


class AssistantSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=2000)
    language = serializers.ChoiceField(choices=["ar", "en"])
    history = AssistantHistoryItem(many=True, required=False, max_length=8, default=list)


class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.CharField()


# --- Output serializers (v1) --------------------------------------------


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ["date", "time", "timezone", "status"]


class RequestEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = RequestEvent
        fields = ["uuid", "event_type", "status", "actor", "created_at"]

    @extend_schema_field(serializers.EmailField(allow_null=True))
    def get_actor(self, obj):
        return obj.actor.email if obj.actor_id else None


def latest_appointment(req):
    """Newest appointment, using the prefetch cache when present (no extra query)."""
    appointments = list(req.appointments.all())
    return max(appointments, key=lambda a: a.pk) if appointments else None


class PublicRequestSerializer(serializers.ModelSerializer):
    """What a customer may see: never the internal note, assignee or raw details."""

    appointment = serializers.SerializerMethodField()

    class Meta:
        model = Request
        fields = ["reference", "kind", "status", "created_at", "reviewed_at", "appointment"]

    @extend_schema_field(AppointmentSerializer(allow_null=True))
    def get_appointment(self, obj):
        appointment = latest_appointment(obj)
        return AppointmentSerializer(appointment).data if appointment else None


class MyRequestSerializer(PublicRequestSerializer):
    class Meta(PublicRequestSerializer.Meta):
        fields = [
            "uuid",
            "reference",
            "kind",
            "audience",
            "organization",
            "status",
            "created_at",
            "reviewed_at",
            "appointment",
        ]


class MyRequestDetailSerializer(MyRequestSerializer):
    events = serializers.SerializerMethodField()

    class Meta(MyRequestSerializer.Meta):
        fields = MyRequestSerializer.Meta.fields + ["events"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_events(self, obj):
        return [{"event_type": e.event_type, "status": e.status, "created_at": e.created_at} for e in obj.events.all()]


class TeamRequestSerializer(serializers.ModelSerializer):
    appointment = serializers.SerializerMethodField()
    assigned_to = serializers.SlugRelatedField(slug_field="email", read_only=True)

    class Meta:
        model = Request
        fields = [
            "uuid",
            "reference",
            "kind",
            "audience",
            "name",
            "email",
            "organization",
            "language",
            "details",
            "status",
            "internal_note",
            "assigned_to",
            "created_at",
            "updated_at",
            "reviewed_at",
            "appointment",
        ]
        read_only_fields = fields

    @extend_schema_field(AppointmentSerializer(allow_null=True))
    def get_appointment(self, obj):
        appointment = latest_appointment(obj)
        return AppointmentSerializer(appointment).data if appointment else None


class TeamRequestDetailSerializer(TeamRequestSerializer):
    events = RequestEventSerializer(many=True, read_only=True)

    class Meta(TeamRequestSerializer.Meta):
        fields = TeamRequestSerializer.Meta.fields + ["events"]
        read_only_fields = fields


class TeamRequestUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Request.Status.choices, required=False)
    internal_note = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    assigned_to = serializers.EmailField(required=False, allow_null=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide status, internal_note or assigned_to.")
        return attrs


def legacy_row(req):
    """Row shape used by the original /team console (snake_case, details as a JSON string)."""
    import json

    appointment = latest_appointment(req)
    return {
        "reference": req.reference,
        "kind": req.kind,
        "audience": req.audience,
        "name": req.name,
        "email": req.email,
        "organization": req.organization,
        "details": json.dumps(req.details, ensure_ascii=False, separators=(",", ":")),
        "status": req.status,
        "created_at": iso(req.created_at),
        "updated_at": iso(req.reviewed_at),
        "internal_note": req.internal_note,
        "date": appointment.date.isoformat() if appointment else None,
        "time": appointment.time if appointment else None,
        "timezone": appointment.timezone if appointment else None,
        "appointment_status": appointment.status if appointment else None,
    }


def valid_future_date(value: str) -> bool:
    """After today (Cairo), within the booking horizon, on a booking weekday and not a blocked day.

    The days, the horizon and the blocked dates come from the site settings (admin). Their defaults are the old rule:
    within 90 days, Sunday to Thursday, nothing blocked.
    """
    try:
        parsed = date_cls.fromisoformat(value)
    except ValueError:
        return False
    if parsed.isoformat() != value:
        return False
    return site_settings.is_bookable_date(parsed)
