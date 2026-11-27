"""Read the team's site settings (booking days and times, blocked days, switches) for the public API.

`get()` returns a small frozen snapshot, cached for 60 seconds. Saving the settings or a blocked day clears the cache
(signals at the bottom), so a change in the admin shows up at once on this server process pool; a process whose cache
entry was just read can lag by at most the 60-second timeout.
With no row yet, the snapshot equals the old hard-coded behaviour: Sunday to Thursday, 10:00 / 11:00 / 12:00 / 14:00 /
15:00 Cairo time, 90 days ahead, nothing blocked, everything switched on.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import BlockedDay, SiteSettings, default_booking_weekdays, default_slot_times

CACHE_KEY = "flowly:site-settings:v1"
CACHE_SECONDS = 60
TIMEZONE = "Africa/Cairo"


@dataclass(frozen=True)
class Snapshot:
    assistant_enabled: bool
    intake_enabled: bool
    weekdays: tuple  # Python weekday numbers, Monday=0 ... Sunday=6
    slot_times: tuple
    horizon_days: int
    blocked: frozenset  # ISO dates ("2026-12-25")


def _load():
    row = SiteSettings.objects.filter(pk=1).first()
    blocked = frozenset(d.isoformat() for d in BlockedDay.objects.values_list("date", flat=True))
    if row is None:
        return Snapshot(True, True, tuple(default_booking_weekdays()), tuple(default_slot_times()), 90, blocked)
    return Snapshot(
        bool(row.assistant_enabled),
        bool(row.intake_enabled),
        tuple(sorted(int(d) for d in row.booking_weekdays)),
        tuple(row.slot_times),
        int(row.booking_horizon_days),
        blocked,
    )


def get():
    snapshot = cache.get(CACHE_KEY)
    if snapshot is None:
        snapshot = _load()
        cache.set(CACHE_KEY, snapshot, timeout=CACHE_SECONDS)
    return snapshot


def clear_cache():
    cache.delete(CACHE_KEY)


def today_cairo():
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def is_bookable_date(value: date, today=None) -> bool:
    """After today, within the horizon, on a booking weekday, and not a blocked day."""
    s = get()
    today = today or today_cairo()
    return (
        today < value <= today + timedelta(days=s.horizon_days)
        and value.weekday() in s.weekdays
        and value.isoformat() not in s.blocked
    )


def is_blocked(value: date) -> bool:
    return value.isoformat() in get().blocked


@receiver(post_save, sender=SiteSettings)
@receiver(post_delete, sender=SiteSettings)
@receiver(post_save, sender=BlockedDay)
@receiver(post_delete, sender=BlockedDay)
def _clear_on_change(sender, **kwargs):
    clear_cache()
