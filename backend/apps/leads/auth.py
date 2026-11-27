"""Team authentication: a staff JWT, or the legacy shared ADMIN_TOKEN bearer when ALLOW_SHARED_ADMIN_TOKEN is True."""

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.utils import constant_time_equals

User = get_user_model()


class TokenOwner:
    """Stand-in principal for the shared ADMIN_TOKEN. Not a database user."""

    pk = None
    uuid = None
    email = "admin-token"
    role = "owner"
    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_deleted = False
    is_superuser = False
    is_staff = False


class AdminTokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        if not settings.ALLOW_SHARED_ADMIN_TOKEN:
            return None
        expected = settings.ADMIN_TOKEN or ""
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if len(expected) < 32 or not header.startswith("Bearer "):
            return None
        supplied = header[7:]
        if constant_time_equals(supplied, expected):
            return (TokenOwner(), supplied)
        return None


class TeamJWTAuthentication(JWTAuthentication):
    """Plain JWT auth, but a bearer that is neither a JWT nor the admin token is a clean 401."""


TEAM_AUTHENTICATION = [AdminTokenAuthentication, TeamJWTAuthentication]


def actor_for(request):
    """The database user to record on events, or None for the shared admin token."""
    user = request.user
    return user if isinstance(user, User) else None


def optional_user(request):
    """Return a verified JWT user for public endpoints, or None (never raises)."""
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return None
    try:
        result = JWTAuthentication().authenticate(request)
    except Exception:  # noqa: BLE001 - public endpoints ignore bad tokens
        return None
    return result[0] if result else None
