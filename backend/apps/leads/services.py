"""Lead intake business logic shared by the legacy (/api) and v1 (/api/v1) endpoints."""

import logging
import uuid
from datetime import date as date_cls
from datetime import datetime
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.utils import send_template_email

from .models import Appointment, Request, RequestEvent

logger = logging.getLogger(__name__)

ACTIVE_APPOINTMENT = ("provisional", "confirmed")


class SlotTaken(Exception):
    """The requested consultation slot is already held by another active request."""


def new_reference() -> str:
    day = datetime.now(dt_timezone.utc).strftime("%Y%m%d")
    return f"FLW-{day}-{uuid.uuid4().hex[:8].upper()}"


def busy_times(date_str: str):
    return list(
        Appointment.objects.filter(date=date_str, status__in=ACTIVE_APPOINTMENT)
        .order_by("time")
        .values_list("time", flat=True)
    )


def find_existing(request_key):
    return Request.objects.filter(pk=request_key).first()


def create_request(data: dict, user=None):
    """Create the request, its first event and (optionally) a provisional appointment.

    Returns (request, appointment|None). Raises SlotTaken on a slot collision.
    """
    key = data["requestKey"]
    date_str, time_str = data.get("date"), data.get("time")
    if (
        date_str
        and time_str
        and Appointment.objects.filter(slot=f"{date_str}T{time_str}", status__in=ACTIVE_APPOINTMENT).exists()
    ):
        raise SlotTaken()

    details = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in data.items()}
    try:
        with transaction.atomic():
            req = Request.objects.create(
                id=key,
                reference=new_reference(),
                kind=data["kind"],
                audience=data["audience"],
                name=data["name"],
                email=data["email"],
                organization=data["organization"],
                language=data["language"],
                consent=True,
                details=details,
                status=Request.Status.PENDING_REVIEW,
                user=user if getattr(user, "is_authenticated", False) else None,
            )
            RequestEvent.objects.create(request=req, event_type="submitted", status=req.status, actor=req.user)
            appointment = None
            if date_str and time_str:
                appointment = Appointment.objects.create(
                    request=req,
                    slot=f"{date_str}T{time_str}",
                    date=date_cls.fromisoformat(date_str),
                    time=time_str,
                    timezone="Africa/Cairo",
                    status=Appointment.Status.PROVISIONAL,
                )
    except IntegrityError:
        if (
            date_str
            and time_str
            and Appointment.objects.filter(slot=f"{date_str}T{time_str}", status__in=ACTIVE_APPOINTMENT).exists()
        ):
            raise SlotTaken()
        existing = find_existing(key)
        if existing:  # lost a race with a retry of the same request
            return existing, existing.appointments.order_by("-pk").first()
        raise
    notify_new_request(req, appointment)
    return req, appointment


def notify_new_request(req: Request, appointment):
    ctx = {"req": req, "appointment": appointment, "arabic": req.language == "ar"}
    subject = "استلمنا طلبك في Flowly" if req.language == "ar" else "We received your Flowly request"
    send_template_email(subject, req.email, "emails/request_received.html", ctx)
    if settings.TEAM_NOTIFY_EMAIL:
        send_template_email(
            f"New Flowly request {req.reference}",
            [e.strip() for e in settings.TEAM_NOTIFY_EMAIL.split(",") if e.strip()],
            "emails/team_alert.html",
            ctx,
        )


def lookup(reference: str, email: str):
    return Request.objects.filter(reference=reference, email__iexact=email).prefetch_related("appointments").first()


def appointment_status_for(status: str) -> str:
    if status in ("declined", "canceled"):
        return Appointment.Status.CANCELED
    if status in ("confirmed", "completed"):
        return Appointment.Status.CONFIRMED
    return Appointment.Status.PROVISIONAL


def update_request(req: Request, *, status=None, internal_note=None, assigned_to=None, assign=False, actor=None):
    """Apply a team update. Raises SlotTaken if re-activating an appointment whose slot was re-booked."""
    previous_status = req.status
    fields = ["updated_at", "reviewed_at"]
    try:
        with transaction.atomic():
            if status is not None:
                req.status = status
                fields.append("status")
            if internal_note is not None:
                note_changed = internal_note != req.internal_note
                req.internal_note = internal_note
                fields.append("internal_note")
            else:
                note_changed = False
            if assign:
                req.assigned_to = assigned_to
                fields.append("assigned_to")
            req.reviewed_at = timezone.now()
            req.save(update_fields=fields)
            if status is not None:
                for appointment in req.appointments.all():
                    appointment.status = appointment_status_for(status)
                    appointment.save(update_fields=["status", "updated_at"])
                if status != previous_status:
                    RequestEvent.objects.create(request=req, event_type="status_changed", status=status, actor=actor)
            if note_changed:
                RequestEvent.objects.create(request=req, event_type="note_updated", status=req.status, actor=actor)
            if assign:
                RequestEvent.objects.create(request=req, event_type="assigned", status=req.status, actor=actor)
    except IntegrityError:
        raise SlotTaken()
    if status is not None and status != previous_status:
        send_status_email(req)
    return req


def send_status_email(req: Request):
    arabic = req.language == "ar"
    subject = f"تحديث على طلبك {req.reference}" if arabic else f"Update on your Flowly request {req.reference}"
    send_template_email(
        subject,
        req.email,
        "emails/status_changed.html",
        {"req": req, "arabic": arabic, "status_label": req.get_status_display()},
    )
