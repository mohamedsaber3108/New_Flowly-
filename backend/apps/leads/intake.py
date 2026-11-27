"""Transport-independent intake operations used by both API generations.

Each function either returns a payload or raises IntakeError(status, message, errors).
Legacy views render {"error": message}; v1 views render the standard envelope.
"""

from datetime import date as date_cls
from datetime import timedelta

from apps.core.exceptions import flatten_errors
from apps.core.throttling import allow_request

from . import assistant as assistant_service
from . import services, site_settings
from .serializers import (
    AssistantSerializer,
    RequestCreateSerializer,
    RequestLookupSerializer,
    latest_appointment,
    valid_future_date,
)

TOO_MANY = "Too many requests. Please try again later."


class IntakeError(Exception):
    def __init__(self, status, message, errors=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.errors = errors


def _appointment_payload(appointment):
    if not appointment:
        return None
    return {
        "date": appointment.date.isoformat(),
        "time": appointment.time,
        "timezone": appointment.timezone,
        "status": appointment.status,
    }


INTAKE_OFF = {
    "en": "New requests are paused for now. Please try again later.",
    "ar": "استقبال الطلبات الجديدة متوقف مؤقتًا. حاول مرة أخرى لاحقًا.",
}
ASSISTANT_OFF = {
    "en": "The assistant is switched off for now. Please use the contact form and the team will reply.",
    "ar": "المساعد متوقف حاليًا. استخدم نموذج التواصل وسيرد عليك الفريق.",
}


def _off_message(texts, payload):
    """The message in the visitor's language; both languages when the request does not say which."""
    language = payload.get("language") if isinstance(payload, dict) else None
    return texts.get(language) or f"{texts['en']} / {texts['ar']}"


def submit_request(request, payload, user=None):
    """Returns (http_status, body)."""
    if not site_settings.get().intake_enabled:  # switched off in the admin: save nothing, say so clearly
        raise IntakeError(503, _off_message(INTAKE_OFF, payload))
    serializer = RequestCreateSerializer(data=payload)
    if not serializer.is_valid():
        raise IntakeError(400, flatten_errors(serializer.errors), serializer.errors)
    data = serializer.validated_data
    if data.get("date") and not valid_future_date(data["date"]):
        horizon = site_settings.get().horizon_days
        message = f"Choose an available future working day within {horizon} days."
        raise IntakeError(400, message, {"date": [message]})
    existing = services.find_existing(data["requestKey"])
    if existing:  # safe retry: same browser key returns the original reference
        return 200, {"reference": existing.reference, "status": existing.status}
    if not allow_request(request, "request"):
        raise IntakeError(429, "Too many requests. Please try again later.")
    try:
        req, appointment = services.create_request(data, user=user)
    except services.SlotTaken:
        raise IntakeError(409, "That time was just requested. Please select another time.")
    return 201, {
        "reference": req.reference,
        "status": req.status,
        "appointment": _appointment_payload(appointment),
    }


def lookup_request(request, payload):
    serializer = RequestLookupSerializer(data=payload)
    if not serializer.is_valid():
        raise IntakeError(400, "Enter your reference and email.", serializer.errors)
    if not allow_request(request, "lookup"):
        raise IntakeError(429, "Too many lookups. Please try again later.")
    data = serializer.validated_data
    req = services.lookup(data["reference"], data["email"])
    if req is None:
        raise IntakeError(404, "No matching request was found. Check the reference and email you submitted.")
    return {
        "reference": req.reference,
        "kind": req.kind,
        "status": req.status,
        "createdAt": _iso(req.created_at),
        "updatedAt": _iso(req.reviewed_at),
        "appointment": _appointment_payload(latest_appointment(req)),
    }


def availability(date_str):
    """Times for one date. `busy` is kept for the existing page; `slots` is the same information with a text label:
    each slot says its time zone and `available` is true or false, so a taken slot can be shown in words."""
    if not date_str:
        raise IntakeError(400, "Invalid consultation date")
    try:
        parsed = date_cls.fromisoformat(date_str)
    except ValueError:
        raise IntakeError(400, "Invalid consultation date")
    snapshot = site_settings.get()
    today = site_settings.today_cairo()
    in_range = (
        parsed.isoformat() == date_str
        and today < parsed <= today + timedelta(days=snapshot.horizon_days)
        and parsed.weekday() in snapshot.weekdays
    )
    if not in_range:
        raise IntakeError(400, "Invalid consultation date")
    base = {"date": date_str, "timezone": site_settings.TIMEZONE}
    if site_settings.is_blocked(parsed):  # a day the team closed: no times, said plainly (the reason stays private)
        return {**base, "busy": [], "slots": [], "closed": True}
    busy = services.busy_times(date_str)
    slots = [
        {"time": t, "available": t not in busy, "label": f"{t} ({site_settings.TIMEZONE})"} for t in snapshot.slot_times
    ]
    return {**base, "busy": busy, "slots": slots, "closed": False}


def assistant_reply(request, payload, user=None):
    serializer = AssistantSerializer(data=payload)
    if not serializer.is_valid():
        raise IntakeError(400, "Invalid message", serializer.errors)
    if not allow_request(request, "assistant"):
        raise IntakeError(429, "Message limit reached. Please try again later.")
    data = serializer.validated_data
    if not site_settings.get().assistant_enabled:
        raise IntakeError(503, _off_message(ASSISTANT_OFF, payload))
    result = assistant_service.answer(data["message"], data["language"], [dict(h) for h in data["history"]])
    from django.conf import settings

    if settings.ASSISTANT_LOG_ENABLED:
        from .models import AssistantMessage

        AssistantMessage.objects.create(
            user=user if getattr(user, "is_authenticated", False) and hasattr(user, "uuid") else None,
            language=data["language"],
            message=data["message"],
            reply=result["reply"],
            mode=result["mode"],
        )
    return result


def _iso(value):
    from apps.core.utils import iso

    return iso(value)
