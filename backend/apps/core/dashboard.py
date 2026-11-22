"""Unfold admin dashboard: operational reporting built from live request data."""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncWeek
from django.urls import reverse
from django.utils import timezone

OPEN_STATUSES = ("pending_review", "in_review", "needs_information", "proposal_preparing", "proposal_sent", "confirmed")


def _breakdown(queryset, field, choices):
    counts = dict(queryset.values_list(field).annotate(n=Count("pk")))
    total = sum(counts.values()) or 1
    changelist = reverse("admin:leads_request_changelist")
    return [
        {
            "label": label,
            "count": counts.get(value, 0),
            "percent": round(counts.get(value, 0) * 100 / total),
            "url": f"{changelist}?{field}__exact={value}",
        }
        for value, label in choices
    ]


def dashboard_callback(request, context):
    from apps.accounts.models import User
    from apps.leads.models import Appointment, Request

    now = timezone.now()
    today = timezone.localdate()
    requests = Request.objects.all()
    last_30 = requests.filter(created_at__gte=now - timedelta(days=30))

    weeks_start = now - timedelta(weeks=8)
    weekly = {}
    for week, n in (
        requests.filter(created_at__gte=weeks_start)
        .annotate(week=TruncWeek("created_at"))
        .values_list("week")
        .annotate(n=Count("pk"))
    ):
        day = timezone.localtime(week).date() if timezone.is_aware(week) else week.date()
        weekly[day] = weekly.get(day, 0) + n
    series, peak = [], 1
    for i in range(7, -1, -1):
        start = today - timedelta(weeks=i)
        start -= timedelta(days=start.weekday())  # Monday, matching TruncWeek
        n = weekly.get(start, 0)
        series.append({"label": start.strftime("%d %b"), "count": n})
        peak = max(peak, n)
    for point in series:
        point["height"] = max(4, round(point["count"] * 100 / peak))

    context.update(
        {
            "flowly_total_requests": requests.count(),
            "flowly_last_30": last_30.count(),
            "flowly_pending": requests.filter(status="pending_review").count(),
            "flowly_open": requests.filter(status__in=OPEN_STATUSES).count(),
            "flowly_upcoming": Appointment.objects.filter(
                status__in=["provisional", "confirmed"], date__gte=today
            ).count(),
            "flowly_customers": User.objects.filter(role="customer", is_deleted=False).count(),
            "flowly_by_status": _breakdown(requests, "status", Request.Status.choices),
            "flowly_by_kind": _breakdown(requests, "kind", Request.Kind.choices),
            "flowly_by_audience": _breakdown(requests, "audience", Request.Audience.choices),
            "flowly_weekly": series,
            "flowly_next_appointments": Appointment.objects.filter(
                status__in=["provisional", "confirmed"], date__gte=today
            )
            .select_related("request")
            .order_by("date", "time")[:6],
            "flowly_recent": requests.select_related("assigned_to").order_by("-created_at")[:8],
            "flowly_pending_url": reverse("admin:leads_request_changelist") + "?status__exact=pending_review",
            "flowly_requests_url": reverse("admin:leads_request_changelist"),
        }
    )
    return context
