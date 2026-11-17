"""Account business logic: tokens, verification emails, password reset, Google sign-in."""

import logging
import secrets
from urllib.parse import urlencode

import requests
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.utils import send_template_email

logger = logging.getLogger(__name__)
User = get_user_model()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
STATE_SALT = "flowly.google.oauth.state"


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def is_email_verified(user):
    return EmailAddress.objects.filter(user=user, email__iexact=user.email, verified=True).exists()


def send_verification_email(user, request=None):
    address, _ = EmailAddress.objects.get_or_create(
        user=user, email=user.email, defaults={"primary": True, "verified": False}
    )
    if address.verified:
        return False
    key = EmailConfirmationHMAC(address).key
    link = f"{settings.SITE_URL}/api/v1/auth/verify-email/{key}/"
    return send_template_email(
        "Verify your Flowly email",
        user.email,
        "emails/verify_email.html",
        {"name": user.first_name or user.email, "link": link},
    )


def confirm_email(key, request=None):
    """Returns the verified EmailAddress or None."""
    confirmation = EmailConfirmationHMAC.from_key(key)
    if confirmation is None:
        return None
    return confirmation.confirm(request)


def send_password_reset(email):
    """Silently does nothing for unknown/disabled accounts (no account enumeration)."""
    user = User.objects.filter(email__iexact=email, is_active=True, is_deleted=False).first()
    if user is None:
        return False
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.SITE_URL}/accounts/reset/{uid}/{token}/"
    return send_template_email(
        "Reset your Flowly password",
        user.email,
        "emails/password_reset.html",
        {"name": user.first_name or user.email, "link": link, "uid": uid, "token": token},
    )


def resolve_reset_user(uid, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True, is_deleted=False)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    return user if default_token_generator.check_token(user, token) else None


# --- Google ---------------------------------------------------------------


class GoogleAuthError(Exception):
    pass


def google_redirect_uri():
    return f"{settings.SITE_URL}/api/v1/auth/social/google/callback/"


def google_authorization_url():
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Google sign-in is not configured.")
    state = signing.dumps(secrets.token_urlsafe(16), salt=STATE_SALT)
    query = urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": google_redirect_uri(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}", state


def verify_state(state):
    try:
        signing.loads(state, salt=STATE_SALT, max_age=600)
    except signing.BadSignature:
        raise GoogleAuthError("Sign-in session expired. Please try again.")


def _google_claims(code=None, id_token=None, redirect_uri=None):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise GoogleAuthError("Google sign-in is not configured.")
    try:
        if code:
            token = requests.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri or google_redirect_uri(),
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            if token.status_code != 200:
                raise GoogleAuthError("Google rejected the authorization code.")
            id_token = token.json().get("id_token")
        info = requests.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token}, timeout=10)
        if info.status_code != 200:
            raise GoogleAuthError("Google identity could not be verified.")
        claims = info.json()
    except requests.RequestException:
        logger.exception("Google OAuth request failed")
        raise GoogleAuthError("Google could not be reached. Please try again.")
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise GoogleAuthError("Google identity was issued for a different application.")
    if str(claims.get("email_verified")).lower() != "true" or not claims.get("email"):
        raise GoogleAuthError("Your Google email address is not verified.")
    return claims


@transaction.atomic
def google_sign_in(code=None, id_token=None, redirect_uri=None):
    claims = _google_claims(code=code, id_token=id_token, redirect_uri=redirect_uri)
    email = claims["email"].lower()
    uid = claims["sub"]
    social = SocialAccount.objects.filter(provider="google", uid=uid).select_related("user").first()
    if social:
        user = social.user
    else:
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email,
                password=None,
                first_name=claims.get("given_name", "")[:150],
                last_name=claims.get("family_name", "")[:150],
                role=User.Role.CUSTOMER,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
        SocialAccount.objects.create(user=user, provider="google", uid=uid, extra_data=claims)
    if user.is_deleted or not user.is_active:
        raise GoogleAuthError("This account is disabled.")
    address, _ = EmailAddress.objects.get_or_create(
        user=user, email=user.email, defaults={"primary": True, "verified": True}
    )
    if not address.verified:
        address.verified = True
        address.save(update_fields=["verified"])
    from apps.leads.models import Request

    Request.objects.filter(user__isnull=True, email__iexact=user.email).update(user=user)
    return user
