"""Two-step verification for owner and staff: TOTP (RFC 6238) plus 10 single-use recovery codes.

No extra package: TOTP is HMAC-SHA1 over a 30-second counter (about 15 lines), checked against the RFC test vectors.
The secret is encrypted at rest with Fernet (the `cryptography` package that is already installed); the key comes from
the env name MFA_ENCRYPTION_KEY. Recovery codes are stored only as an HMAC.

shortcut: no QR image (that needs another package). The enrolment page shows the secret as text and an otpauth:// link,
which every authenticator app accepts and which also works with a screen reader.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from .events import log_event
from .models import MfaDevice, RecoveryCode

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1  # accept the previous and the next 30 s step (clock drift)
RECOVERY_CODE_COUNT = 10
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alike characters
TEAM_ROLES = ("owner", "staff")


class AlreadyEnrolled(Exception):
    """The user already has a confirmed device. It can only be reset by an owner (admin action)."""


class NotEnrolling(Exception):
    """No pending enrolment to confirm."""


# --- who needs a second factor -----------------------------------------------------------------------------------


def is_team_user(user):
    return bool(user and (user.is_superuser or getattr(user, "role", "") in TEAM_ROLES))


def has_confirmed_device(user):
    return MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def enrollment_required(user):
    """Owner/staff with no confirmed device, while the owner has switched REQUIRE_STAFF_MFA on."""
    return bool(settings.REQUIRE_STAFF_MFA and is_team_user(user) and not has_confirmed_device(user))


def second_factor_needed(user):
    """A code is asked for at sign-in when the user has a confirmed device (always) or the rule is on for team users."""
    return bool(is_team_user(user) and (settings.REQUIRE_STAFF_MFA or has_confirmed_device(user)))


# --- encryption --------------------------------------------------------------------------------------------------


def _fernet():
    key = settings.MFA_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured("MFA_ENCRYPTION_KEY is not set.")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("MFA_ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encrypt_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured("MFA secret cannot be decrypted with MFA_ENCRYPTION_KEY.") from exc


# --- TOTP (RFC 6238) ---------------------------------------------------------------------------------------------


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code_for_step(secret_b32, step):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**DIGITS)
    return f"{number:0{DIGITS}d}"


def totp_now(secret_b32, now=None):
    return _code_for_step(secret_b32, int((time.time() if now is None else now) // STEP_SECONDS))


def match_step(secret_b32, code, after_step=0, now=None):
    """The 30 s step the code belongs to (within the drift window and newer than `after_step`), or None."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        if step > after_step and hmac.compare_digest(_code_for_step(secret_b32, step), code):
            return step
    return None


def otpauth_uri(user, secret_b32):
    label = quote(f"Flowly:{user.email}")
    return (
        f"otpauth://totp/{label}?secret={secret_b32}&issuer=Flowly&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


# --- recovery codes ----------------------------------------------------------------------------------------------


def _normalise_recovery(code):
    return "".join(ch for ch in (code or "").lower() if ch.isalnum())


def _digest(code):
    return hmac.new(settings.SECRET_KEY.encode(), _normalise_recovery(code).encode(), hashlib.sha256).hexdigest()


def _new_recovery_code():
    raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


# --- enrolment ---------------------------------------------------------------------------------------------------


def start_enrollment(user):
    """Create (or replace) the PENDING device and return (secret, otpauth link). A confirmed device is never replaced
    here: someone who only knows the password must not be able to swap the second factor."""
    if has_confirmed_device(user):
        raise AlreadyEnrolled()
    secret = new_secret()
    MfaDevice.objects.update_or_create(
        user=user, defaults={"secret": encrypt_secret(secret), "confirmed_at": None, "last_step": 0}
    )
    log_event("mfa.enrol_started", user_id=user.pk, email=user.email)
    return secret, otpauth_uri(user, secret)


def confirm_enrollment(user, code):
    """Prove the first code, switch the device on, return the recovery codes (shown once). None if the code is wrong."""
    device = MfaDevice.objects.filter(user=user, confirmed_at__isnull=True).first()
    if device is None:
        raise NotEnrolling()
    step = match_step(decrypt_secret(device.secret), code)
    if step is None:
        return None
    codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    with transaction.atomic():
        device.confirmed_at = timezone.now()
        device.last_step = step
        device.save(update_fields=["confirmed_at", "last_step"])
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create([RecoveryCode(user=user, digest=_digest(c)) for c in codes])
    log_event("mfa.enrol_confirmed", user_id=user.pk, email=user.email)
    return codes


def reset_device(user, by=""):
    """Owner action (or the break-glass command): remove the device and recovery codes so the user can enrol again.
    `by` says who did it, for the log line."""
    MfaDevice.objects.filter(user=user).delete()
    RecoveryCode.objects.filter(user=user).delete()
    log_event("mfa.reset", level=logging.WARNING, user_id=user.pk, email=user.email, by=by)


# --- sign-in check -----------------------------------------------------------------------------------------------


def verify_second_factor(user, code):
    """True if `code` is a fresh authenticator code or an unused recovery code. Each one works exactly once."""
    code = (code or "").strip()
    if not code:
        return False
    device = MfaDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        return False
    step = match_step(decrypt_secret(device.secret), code, after_step=device.last_step)
    if step is not None:
        # Compare-and-set: two requests with the same code cannot both pass.
        return MfaDevice.objects.filter(pk=device.pk, last_step__lt=step).update(last_step=step) == 1
    if not _normalise_recovery(code):
        return False
    used = RecoveryCode.objects.filter(user=user, digest=_digest(code), used_at__isnull=True).update(
        used_at=timezone.now()
    )
    return used == 1
