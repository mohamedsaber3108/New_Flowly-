"""Lead pipeline numbers for the admin dashboard (FL-15). The definitions are written here once.

* **Source** of a request: its `utm_source`, trimmed and in lower case. Only the characters `a-z 0-9 _ . -` are kept
  (at most 50): any other value is stored as "other" (see `clean_source`), and a request without one counts as
  "direct". The dashboard shows the 10 sources with the most requests and adds everything else, with "other", as one
  row called "other".
* **Quote stage**: the request's `quote_status` (none, sent, accepted, lost). Every request has exactly one.
* **Time to first reply**: `first_reply_at - created_at` for requests created in the last 30 days that have a
  `first_reply_at`. `first_reply_at` is set once, at the first status change made by the team (the change that also
  emails the customer). A note, an assignment or a quote change alone does not count. The number shown is the
  median in hours. Requests created in the window with no reply yet are counted separately as "waiting" and are not
  in the median.
* **Win rate** of a source: accepted / (accepted + lost), over all requests of that source ever. Requests whose
  quote is still "none" or "sent" are undecided and are left out of both sides. A source with no decided request
  has no rate (None), not 0.

Counts are made by the database (`values().annotate(Count)`), not by looping over every request.
Everything here is team-only data. None of it may be returned by a customer-facing view.
"""

import re
from datetime import timedelta
from statistics import median

from django.db.models import Count
from django.utils import timezone

from .models import Request

DIRECT = "direct"
OTHER = "other"
TOP_SOURCES = 10
WINDOW_DAYS = 30
SOURCE_RE = re.compile(r"[a-z0-9_.-]{1,50}")


def clean_source(value):
    """A UTM source as it is stored: "" if empty, the lower-case text if it only has a-z 0-9 _ . - (up to 50
    characters), otherwise "other". A visitor can type anything into a link, so nothing else is kept."""
    text = (value or "").strip().lower()
    if not text:
        return ""
    return text if SOURCE_RE.fullmatch(text) else OTHER


def source_of(utm_source):
    """The source name used for grouping."""
    return clean_source(utm_source) or DIRECT


def quote_stage_counts(queryset=None):
    """[{"value", "label", "count"}] for every quote stage, in stage order, zero counts included."""
    queryset = Request.objects.all() if queryset is None else queryset
    counts = {row["quote_status"]: row["n"] for row in queryset.values("quote_status").annotate(n=Count("pk"))}
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


def _row(source, total, won, lost):
    decided = won + lost
    return {
        "source": source,
        "total": total,
        "won": won,
        "lost": lost,
        "rate": round(won * 100 / decided) if decided else None,
    }


def win_rate_by_source(limit=TOP_SOURCES):
    """[{"source", "total", "won", "lost", "rate"}] (rate is a whole percent or None): the `limit` sources with the
    most requests, then one "other" row for every other source (and for values stored as "other")."""
    groups = {}
    grouped = Request.objects.values("utm_source", "quote_status").annotate(n=Count("pk"))
    for row in grouped:  # one row per (source, quote stage): a handful, not one per request
        entry = groups.setdefault(source_of(row["utm_source"]), {"total": 0, "won": 0, "lost": 0})
        entry["total"] += row["n"]
        entry["won"] += row["n"] if row["quote_status"] == Request.QuoteStatus.ACCEPTED else 0
        entry["lost"] += row["n"] if row["quote_status"] == Request.QuoteStatus.LOST else 0
    rest = sorted(((s, v) for s, v in groups.items() if s != OTHER), key=lambda item: (-item[1]["total"], item[0]))
    rows = [_row(s, v["total"], v["won"], v["lost"]) for s, v in rest[:limit]]
    merged = [v for _, v in rest[limit:]] + ([groups[OTHER]] if OTHER in groups else [])
    if merged:
        rows.append(_row(OTHER, *(sum(v[k] for v in merged) for k in ("total", "won", "lost"))))
    return rows
