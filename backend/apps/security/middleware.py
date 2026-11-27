"""Django admin session limits for staff: 30 minutes idle, 8 hours in all (settings ADMIN_SESSION_*_SECONDS).

Only staff sessions are touched. Customers and the team console use JWT, not this session. When the limit is
reached the session is ended and the person is sent to the admin sign-in page with ?expired=1.
The admin pages show a notice 5 minutes before the idle limit, with a "Stay signed in" button
(static/security/admin-idle.js, added through UNFOLD["SCRIPTS"] in config/unfold.py). The portal and /team use JWT
and have no idle sign-out, so they need no notice.
"""

import time
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect

STARTED = "staff_session_started"
LAST_SEEN = "staff_session_last_seen"
TOUCH_EVERY = 60  # write the session at most once a minute
WARNING_TEXT = "You will be signed out in 1 minute because of inactivity."


class StaffSessionLimitsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            now = int(time.time())
            started = request.session.get(STARTED, now)
            last_seen = request.session.get(LAST_SEEN, now)
            if (
                now - started > settings.ADMIN_SESSION_MAX_SECONDS
                or now - last_seen > settings.ADMIN_SESSION_IDLE_SECONDS
            ):
                logout(request)  # flushes the session
                login_url = f"/{settings.ADMIN_URL}login/?expired=1&next={quote(request.get_full_path())}"
                return HttpResponseRedirect(login_url)
            if STARTED not in request.session:
                request.session[STARTED] = started
            if now - last_seen >= TOUCH_EVERY or LAST_SEEN not in request.session:
                request.session[LAST_SEEN] = now
        return self.get_response(request)
