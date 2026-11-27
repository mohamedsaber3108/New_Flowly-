"""Sign-in lockout shared by all entrances.

* 5 failed sign-ins for one email from one IP address within 15 minutes lock THAT email from THAT address for
  15 minutes. Someone failing on purpose from another address cannot lock a known team address out.
* One IP address that fails 20 times within 15 minutes (across any emails) is locked for 15 minutes.
* One email that fails 50 times within 15 minutes from many addresses together is locked for 15 minutes for everyone
  (guessing spread over many addresses). The number is high so that locking a person out on purpose needs a lot of
  addresses.

Counters live in the Django cache (the database cache table in production). The Django admin login, the API login
(/team and the account portal), the enrolment door and Google sign-in all use this module through gate.py.
"""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

from .events import log_event

LOCK_MESSAGE = "Too many failed sign-in attempts. Try again in 15 minutes."


def _digest(*parts):
    return hashlib.sha256("|".join((p or "").strip().lower() for p in parts).encode()).hexdigest()[:40]


def _key(kind, *parts):
    return f"signin:{kind}:{_digest(*parts)}"


def is_locked(email, ip):
    return bool(
        cache.get(_key("lock-pair", email, ip))
        or cache.get(_key("lock-ip", ip))
        or cache.get(_key("lock-email", email))
    )


def _count(kind, limit, *parts):
    """Count one failure for this counter. True when it reached the limit (and the counter restarts)."""
    seconds = settings.LOGIN_LOCKOUT_SECONDS
    key = _key(kind, *parts)
    cache.add(key, 0, seconds)
    try:
        count = cache.incr(key)
    except ValueError:  # the key expired between add and incr
        cache.set(key, 1, seconds)
        count = 1
    if count >= limit:
        cache.delete(key)
        return True
    return False


def register_failure(email, ip):
    """Count one failed sign-in on every counter; start a lock where a limit is reached."""
    seconds = settings.LOGIN_LOCKOUT_SECONDS
    if _count("fails-pair", settings.LOGIN_LOCKOUT_ATTEMPTS, email, ip):
        cache.set(_key("lock-pair", email, ip), 1, seconds)
        log_event("signin.locked", scope="email+ip", email=email, ip=ip, minutes=seconds // 60, level=logging.WARNING)
    if _count("fails-ip", settings.LOGIN_LOCKOUT_IP_ATTEMPTS, ip):
        cache.set(_key("lock-ip", ip), 1, seconds)
        log_event("signin.locked", scope="ip", ip=ip, minutes=seconds // 60, level=logging.WARNING)
    if _count("fails-email", settings.LOGIN_LOCKOUT_EMAIL_ATTEMPTS, email):
        cache.set(_key("lock-email", email), 1, seconds)
        log_event("signin.locked", scope="email", email=email, minutes=seconds // 60, level=logging.WARNING)


def reset(email, ip):
    """A successful sign-in clears the count for this email from this address (the per-IP and per-email totals stay)."""
    cache.delete(_key("fails-pair", email, ip))
