"""Server-side limits for team cookie sessions (FL-22b): idle 30 minutes, absolute 8 hours (ADMIN_FOUNDATION s.9).

A team sign-in puts two claims in the refresh token (and so in every access token made from it, and in every token a
refresh rotates to):
* `auth_time`: when the person really signed in (seconds). The session ends 8 hours after it
  (ADMIN_SESSION_MAX_SECONDS), however busy the person is.
* `sid`: a random session id. The time of the last activity is kept in the cache under that id and is moved forward by
  each authenticated team request, at most once a minute. The session ends after 30 minutes without activity
  (ADMIN_SESSION_IDLE_SECONDS). The cache entry lives as long as the longest possible session, and the idle test is a
  comparison of times, so "idle" and "entry lost" are both a refusal (fail closed: the person signs in again).

The check runs on every cookie-authenticated team request and on every refresh. A refusal is a 401 with the code
`session_expired` (8 hours, or a team token without these claims, for example one issued before this change) or
`session_idle`, so the console can say which. Customers' tokens carry no `sid` and are never checked.
"""

import time
import uuid

from django.conf import settings
from django.core.cache import cache
from rest_framework import exceptions

TOUCH_EVERY = 60  # move "last seen" forward at most once a minute


class SessionLimit(exceptions.AuthenticationFailed):
    """The team session is over. `code` is `session_expired` or `session_idle`."""

    def __init__(self, code, detail):
        super().__init__(detail, code)


def _now():
    return time.time()  # one place to replace in tests


def _key(sid):
    return f"staff-session:{sid}:seen"


def new_session_claims():
    """The claims for a team sign-in, and the first "last seen" mark."""
    now = int(_now())
    sid = uuid.uuid4().hex
    cache.set(_key(sid), now, timeout=settings.ADMIN_SESSION_MAX_SECONDS + 3600)
    return {"auth_time": now, "sid": sid}


def check(payload, *, touch=True):
    """Raise SessionLimit if the session behind this token is over; otherwise note the activity."""
    auth_time, sid = payload.get("auth_time"), payload.get("sid")
    if not isinstance(auth_time, (int, float)) or not isinstance(sid, str):
        raise SessionLimit("session_expired", "Your session ended. Sign in again.")
    now = _now()
    if now - auth_time > settings.ADMIN_SESSION_MAX_SECONDS:
        hours = settings.ADMIN_SESSION_MAX_SECONDS // 3600
        raise SessionLimit("session_expired", f"Your session ended after {hours} hours. Sign in again.")
    last_seen = cache.get(_key(sid))
    if last_seen is None or now - last_seen > settings.ADMIN_SESSION_IDLE_SECONDS:
        minutes = settings.ADMIN_SESSION_IDLE_SECONDS // 60
        raise SessionLimit(
            "session_idle", f"You were signed out after {minutes} minutes without activity. Sign in again."
        )
    if touch and now - last_seen >= TOUCH_EVERY:
        cache.set(_key(sid), int(now), timeout=settings.ADMIN_SESSION_MAX_SECONDS + 3600)
