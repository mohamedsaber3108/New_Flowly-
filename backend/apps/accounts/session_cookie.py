"""Staff sign-in as cookies instead of tokens a page script can read (FL-22).

Owner, staff and viewer accounts get their access and refresh tokens in httpOnly, Secure, SameSite=Strict cookies and
the JSON body carries no token. Customers are unchanged (tokens in the body, bearer header).

* The access cookie is sent on `/api/`, the refresh cookie only on `/api/v1/auth/` (refresh and logout).
* A request that is signed in by cookie and changes data (anything but GET, HEAD, OPTIONS) must carry the Django
  CSRF token in the `X-CSRFToken` header, matching the `csrftoken` cookie (double submit). Without it: 403.
* A staff bearer header is refused unless `ALLOW_STAFF_BEARER=True` (off by default): staff use the cookie.
"""

from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication

from . import session_limits

ACCESS_COOKIE = "flowly_staff_access"
REFRESH_COOKIE = "flowly_staff_refresh"
ACCESS_PATH = "/api/"
REFRESH_PATH = "/api/v1/auth/"
STAFF_ROLES = ("owner", "staff", "viewer")


def is_staff_session(user):
    """True for accounts that use the team console (they get cookies, not tokens in the body)."""
    return bool(user and (user.is_superuser or user.is_staff or getattr(user, "role", "") in STAFF_ROLES))


def _cookie_options(path, seconds):
    return {
        "max_age": int(seconds),
        "httponly": True,
        "secure": settings.STAFF_COOKIE_SECURE,
        "samesite": "Strict",
        "path": path,
    }


def set_staff_session(response, request, tokens):
    """Put the token pair in cookies on `response`, and hand out the CSRF token the page must echo back."""
    access_seconds = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
    response.set_cookie(ACCESS_COOKIE, tokens["access"], **_cookie_options(ACCESS_PATH, access_seconds))
    # The refresh cookie lasts STAFF_SESSION_IDLE_SECONDS from the last refresh, so a session left alone ends after
    # that (same default as the admin: 30 minutes). The server enforces the same idle limit and an 8-hour absolute
    # limit itself, whatever the browser does with the cookie (apps/accounts/session_limits.py, FL-22b).
    response.set_cookie(
        REFRESH_COOKIE, tokens["refresh"], **_cookie_options(REFRESH_PATH, settings.STAFF_SESSION_IDLE_SECONDS)
    )
    get_token(request)  # makes Django's CSRF middleware set the readable `csrftoken` cookie on this response
    return response


def clear_staff_session(response):
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_PATH, samesite="Strict")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, samesite="Strict")
    return response


def enforce_csrf(request):
    """The same double-submit check Django's session login uses. Raises 403 when the header does not match."""
    check = CSRFCheck(lambda r: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f"CSRF check failed: {reason}")


class CookieJWTAuthentication(JWTAuthentication):
    """The JWT from the Authorization header (customers; staff only if ALLOW_STAFF_BEARER) or else from the staff
    access cookie, which also needs the CSRF header on a request that changes data."""

    def authenticate(self, request):
        if self.get_header(request) is not None:
            result = super().authenticate(request)
            if result and is_staff_session(result[0]):
                if not settings.ALLOW_STAFF_BEARER:
                    raise exceptions.AuthenticationFailed(
                        "Team accounts sign in with the browser session, not a token.", "staff_bearer_refused"
                    )
                if result[1].payload.get("sid"):  # a token from a team sign-in carries the session limits
                    session_limits.check(result[1].payload)
            return result
        raw = request.COOKIES.get(ACCESS_COOKIE)
        if not raw:
            return None
        token = self.get_validated_token(raw)
        enforce_csrf(request)
        user = self.get_user(token)
        if is_staff_session(user):  # FL-22b: idle and 8-hour limits; a cookie without session claims is refused
            session_limits.check(token.payload)
        return user, token
