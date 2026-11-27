"""Sign-in lockout shared by all entrances: 5 failures in 15 minutes lock the account's sign-in for 15 minutes.

The counter lives in the Django cache (the database cache table in production), keyed by the email address, so the
Django admin login, the API login (/team and the account portal) and the Google sign-in count together.
shortcut: the counter is keyed by email only, so someone who knows a team address can lock that person out for
15 minutes by failing on purpose. nginx limit_req and the login throttle slow that down. Upgrade to email + IP
keys (or an alert) if it happens in practice.
"""

import hashlib

from django.conf import settings
from django.core.cache import cache

LOCK_MESSAGE = "Too many failed sign-in attempts. Try again in 15 minutes."


def _key(kind, email):
    digest = hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:40]
    return f"signin:{kind}:{digest}"


def is_locked(email):
    return bool(cache.get(_key("lock", email)))


def register_failure(email):
    """Count one failed sign-in. The 5th inside the window starts the lock."""
    attempts = settings.LOGIN_LOCKOUT_ATTEMPTS
    seconds = settings.LOGIN_LOCKOUT_SECONDS
    key = _key("fails", email)
    cache.add(key, 0, seconds)
    try:
        count = cache.incr(key)
    except ValueError:  # the key expired between add and incr
        cache.set(key, 1, seconds)
        count = 1
    if count >= attempts:
        cache.set(_key("lock", email), 1, seconds)
        cache.delete(key)


def reset(email):
    cache.delete(_key("fails", email))
