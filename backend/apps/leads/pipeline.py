"""Lead pipeline numbers for the admin dashboard (FL-15). The definitions are written here once.

* **Source** of a request: its `utm_source` (lower case, trimmed). A request without one counts as "direct".
* **Quote stage**: the request's `quote_status` (none, sent, accepted, lost). Every request has exactly one.
* **Time to first reply**: `first_reply_at - created_at` for requests created in the last 30 days that have a
  `first_reply_at`. `first_reply_at` is set once, by the first status change or note written by the team
  (an assignment alone does not count). The number shown is the median in hours. Requests created in the window
  with no reply yet are counted separately as "waiting" and are not in the median.
* **Win rate** of a source: accepted / (accepted + lost), over all requests of that source ever. Requests whose
  quote is still "none" or "sent" are undecided and are left out of both sides. A source with no decided request
  has no rate (None), not 0.

Everything here is team-only data. None of it may be returned by a customer-facing view.
"""

from datetime import timedelta
from statistics import median

from django.utils import timezone

from .models import Request

DIRECT = "direct"
WINDOW_DAYS = 30


def source_of(utm_source):
    """The source name used for grouping."""
    return (utm_source or "").strip().lower() or DIRECT


def quote_stage_counts(queryset=None):
    """[{"value", "label", "count"}] for every quote stage, in stage order, zero counts included."""
    queryset = Request.objects.all() if queryset is None else queryset
    counts = {}
    for stage in queryset.values_list("quote_status", flat=True):
        counts[stage] = counts.get(stage, 0) + 1
    return [
        {"value": value, "label": label, "count": counts.get(value, 0)} for value, label in Request.QuoteStatus.choices
    ]


def first_reply_summary(now=None, days=WINDOW_DAYS):
    """{"median_hours": float|None, "replied": int, "waiting": int} for requests created in the last `days` days."""
    now = now or timezone.now()
    window = Request.objects.filter(created_at__gte=now - timedelta(days=days))
    hours = [
        (replied - created).total_seconds() / 3600
        for created, replied in window.filter(first_reply_at__isnull=False).values_list("created_at", "first_reply_at")
    ]
    return {
        "median_hours": round(median(hours), 1) if hours else None,
        "replied": len(hours),
        "waiting": window.filter(first_reply_at__isnull=True).count(),
    }


def win_rate_by_source():
    """[{"source", "total", "won", "lost", "rate"}] (rate is a whole percent or None), most requests first."""
    rows = {}
    for utm_source, quote in Request.objects.values_list("utm_source", "quote_status"):
        row = rows.setdefault(source_of(utm_source), {"total": 0, "won": 0, "lost": 0})
        row["total"] += 1
        row["won"] += quote == Request.QuoteStatus.ACCEPTED
        row["lost"] += quote == Request.QuoteStatus.LOST
    result = []
    for source, row in rows.items():
        decided = row["won"] + row["lost"]
        result.append({"source": source, **row, "rate": round(row["won"] * 100 / decided) if decided else None})
    return sorted(result, key=lambda r: (-r["total"], r["source"]))
