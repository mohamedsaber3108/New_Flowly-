"""Lead intake business logic shared by the legacy (/api) and v1 (/api/v1) endpoints."""

import logging
import uuid
from datetime import date as date_cls
from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import service as audit
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
                source_page=data.get("sourcePage", ""),
                utm_source=data.get("utmSource", ""),
                utm_medium=data.get("utmMedium", ""),
                utm_campaign=data.get("utmCampaign", ""),
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
        # The alert gets plain facts only, never the request object: no name, email, phone, organization or text.
        created = req.created_at.astimezone(ZoneInfo("Africa/Cairo")).strftime("%Y-%m-%d %H:%M")
        alert = {
            "reference": req.reference,
            "kind": req.get_kind_display(),
            "audience": req.get_audience_display(),
            "created": created,
            "admin_link": f"{settings.SITE_URL}/{settings.ADMIN_URL}leads/request/{req.pk}/change/",
            "team_link": f"{settings.FRONTEND_URL}/team",
        }
        send_template_email(
            f"New Flowly request {req.reference} / طلب جديد على Flowly",
            [e.strip() for e in settings.TEAM_NOTIFY_EMAIL.split(",") if e.strip()],
            "emails/team_alert.html",
            alert,
        )


def lookup(reference: str, email: str):
    return Request.objects.filter(reference=reference, email__iexact=email).prefetch_related("appointments").first()


def appointment_status_for(status: str) -> str:
    if status in ("declined", "canceled"):
        return Appointment.Status.CANCELED
    if status in ("confirmed", "completed"):
        return Appointment.Status.CONFIRMED
    return Appointment.Status.PROVISIONAL


def _plain(value):
    """A value as the audit log stores it (dates as ISO text)."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def update_request(
    req: Request,
    *,
    status=None,
    internal_note=None,
    assigned_to=None,
    assign=False,
    quote_status=None,
    value_range=None,
    next_follow_up=None,
    set_follow_up=False,
    actor=None,
):
    """Apply a team update. Raises SlotTaken if re-activating an appointment whose slot was re-booked.

    Pipeline fields (FL-15): `quote_status` and `value_range` (None = leave as is; "" clears the value range) and
    `next_follow_up` (a date or None; only applied when `set_follow_up=True`, so None can mean "clear it").
    `first_reply_at` is set once, at the first status change by the team (the change that emails the customer);
    a note, an assignment or a quote change alone does not set it.
    """
    previous_status = req.status
    previous_note = req.internal_note
    previous_assignee = req.assigned_to.email if req.assigned_to_id else None
    fields = ["updated_at", "reviewed_at"]
    pipeline_before, pipeline_after = {}, {}
    for name, wanted, applies in (
        ("quote_status", quote_status, quote_status is not None),
        ("value_range", value_range, value_range is not None),
        ("next_follow_up", next_follow_up, set_follow_up),
    ):
        if applies and getattr(req, name) != wanted:
            pipeline_before[name], pipeline_after[name] = getattr(req, name), wanted
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
            for name, value in pipeline_after.items():
                setattr(req, name, value)
                fields.append(name)
            req.reviewed_at = timezone.now()
            if req.first_reply_at is None and status is not None and status != previous_status:
                req.first_reply_at = req.reviewed_at
                fields.append("first_reply_at")
            req.save(update_fields=fields)
            if pipeline_after:
                RequestEvent.objects.create(request=req, event_type="pipeline_updated", status=req.status, actor=actor)
                audit.record(
                    audit.A.REQUEST_PIPELINE,
                    actor=actor,
                    target=req,
                    target_id=req.reference,
                    before={k: _plain(v) for k, v in pipeline_before.items()},
                    after={k: _plain(v) for k, v in pipeline_after.items()},
                )
            if status is not None:
                for appointment in req.appointments.all():
                    appointment.status = appointment_status_for(status)
                    appointment.save(update_fields=["status", "updated_at"])
                if status != previous_status:
                    RequestEvent.objects.create(request=req, event_type="status_changed", status=status, actor=actor)
                    audit.record(
                        audit.A.REQUEST_STATUS,
                        actor=actor,
                        target=req,
                        target_id=req.reference,
                        before={"status": previous_status},
                        after={"status": status},
                    )
            if note_changed:
                RequestEvent.objects.create(request=req, event_type="note_updated", status=req.status, actor=actor)
                audit.record(
                    audit.A.REQUEST_NOTE,
                    actor=actor,
                    target=req,
                    target_id=req.reference,
                    before={"internal_note": previous_note},
                    after={"internal_note": internal_note},
                )
            if assign:
                RequestEvent.objects.create(request=req, event_type="assigned", status=req.status, actor=actor)
                audit.record(
                    audit.A.REQUEST_ASSIGN,
                    actor=actor,
                    target=req,
                    target_id=req.reference,
                    before={"assigned_to": previous_assignee},
                    after={"assigned_to": assigned_to.email if assigned_to else None},
                )
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
