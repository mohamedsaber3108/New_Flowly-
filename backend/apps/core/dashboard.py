"""Unfold admin dashboard callback: request pipeline counters."""


def dashboard_callback(request, context):
    from django.db.models import Count

    from apps.leads.models import Appointment, Request

    by_status = dict(Request.objects.values_list("status").annotate(n=Count("id")))
    context.update(
        {
            "flowly_total_requests": Request.objects.count(),
            "flowly_pending": by_status.get("pending_review", 0),
            "flowly_in_progress": sum(
                by_status.get(s, 0) for s in ("in_review", "needs_information", "proposal_preparing", "proposal_sent")
            ),
            "flowly_upcoming": Appointment.objects.filter(status__in=["provisional", "confirmed"]).count(),
        }
    )
    return context
