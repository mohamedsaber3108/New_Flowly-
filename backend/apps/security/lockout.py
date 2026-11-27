"""Sign-in lockout shared by all entrances.

* 5 failed sign-ins for one email from one IP address within 15 minutes lock THAT email from THAT address for
  15 minutes. Someone failing on purpose from another address cannot lock a known team address out.
* One IP address that fails 20 times within 15 minutes (across any emails) is locked for 15 minutes.
* One email that fails 50 times within 15 minutes from many addresses together is locked for 15 minutes for everyone
  (guessing spread over many addresses). The number is high so that locking someone out on purpose needs many
  addresses (about 10 addresses with 5 tries each is enough, which is accepted: see the PR). An owner can clear it
  (`clear_email`, the admin action "Clear sign-in lock").

Counters live in the Django cache (the database cache table in production). The Django admin login, the API login
(/team and the account portal), the enrolment door and Google sign-in all use this module through gate.py.

Every write passes an explicit timeout. DatabaseCache.incr() would store the counter again with the default
timeout (300 s), which could shrink the 15-minute window, so a counter is kept as (count, window start) and written
back with the time that is left of the window.
shortcut: the read-then-write is not atomic, so two failures at the very same moment can count as one. That only ever
lets an attacker try a handful more passwords; upgrade to a database counter if it matters.
"""

import hashlib
import logging
import time

from django.conf import settings
from django.core.cache import cache

from apps.audit import service as audit

from .events import log_event, mask_email

LOCK_MESSAGE = "Too many failed sign-in attempts. Try again in 15 minutes."


def _digest(*parts):
    return hashlib.sha256("|".join((p or "").strip().lower() for p in parts).encode()).hexdigest()[:40]


def _generation(email):
    """Bumped by clear_email(): counters and locks of an older generation are simply never read again."""
    return str(cache.get(f"signin:gen:{_digest(email)}", 0))


def _email_key(kind, email, ip=None):
    parts = (email, ip, _generation(email)) if ip is not None else (email, _generation(email))
    return f"signin:{kind}:{_digest(*parts)}"


def _ip_key(kind, ip):
    return f"signin:{kind}:{_digest(ip)}"


def is_locked(email, ip):
    return bool(
        cache.get(_email_key("lock-pair", email, ip))
        or cache.get(_ip_key("lock-ip", ip))
        or cache.get(_email_key("lock-email", email))
    )


def _count(key, limit):
    """Count one failure on this counter. True when it reached the limit (the counter then restarts)."""
    seconds = settings.LOGIN_LOCKOUT_SECONDS
    now = time.time()
    count, started = cache.get(key) or (0, now)
    if now - started >= seconds:  # the 15 minutes since the first failure are over: a new window
        count, started = 0, now
    count += 1
    if count >= limit:
        cache.delete(key)
        return True
    cache.set(key, (count, started), timeout=max(1, int(started + seconds - now) + 1))
    return False


def register_failure(email, ip):
    """Count one failed sign-in on every counter; start a lock where a limit is reached."""
    seconds = settings.LOGIN_LOCKOUT_SECONDS
    shown = mask_email(email)  # the typed text can be a password: never log it as typed
    if _count(_email_key("fails-pair", email, ip), settings.LOGIN_LOCKOUT_ATTEMPTS):
        cache.set(_email_key("lock-pair", email, ip), 1, timeout=seconds)
        _locked("email+ip", shown, ip, seconds)
    if _count(_ip_key("fails-ip", ip), settings.LOGIN_LOCKOUT_IP_ATTEMPTS):
        cache.set(_ip_key("lock-ip", ip), 1, timeout=seconds)
        _locked("ip", "", ip, seconds)
    if _count(_email_key("fails-email", email), settings.LOGIN_LOCKOUT_EMAIL_ATTEMPTS):
        cache.set(_email_key("lock-email", email), 1, timeout=seconds)
        _locked("email", shown, "", seconds)


def _locked(scope, shown_email, ip, seconds):
    """A lock has started: one log line and one audit entry. Never the typed text (it can be a password): the email
    is masked. The audit entry is best effort (a lock must still start if the audit table is not writable)."""
    log_event("signin.locked", scope=scope, email=shown_email, ip=ip, minutes=seconds // 60, level=logging.WARNING)
    audit.record(
        audit.A.SIGNIN_LOCKED,
        target_type="signin",
        target_id=shown_email or ip or scope,
        after={"scope": scope, "email": shown_email, "ip": ip, "minutes": seconds // 60},
        result=audit.R.DENIED,
    )


def reset(email, ip):
    """A successful sign-in clears the count for this email from this address (the per-IP and per-email totals stay)."""
    cache.delete(_email_key("fails-pair", email, ip))


def clear_email(email, by="", actor=None):
    """Owner action: forget every count and lock for this email, from every address. A lock on an IP address stays.
    Fail closed: the audit entry comes first, so if it cannot be written the lock is not cleared."""
    audit.record(
        audit.A.SIGNIN_UNLOCKED,
        actor=actor,
        target_type="signin",
        target_id=mask_email(email),
        after={"email": mask_email(email), "by": by},
        sensitive=True,
    )
    key = f"signin:gen:{_digest(email)}"
    cache.set(key, int(cache.get(key, 0)) + 1, timeout=None)  # never expires: an old generation must stay dead
    log_event("signin.lock_cleared", email=mask_email(email), by=by)
