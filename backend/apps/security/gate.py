"""The one check every sign-in entrance calls, so they cannot drift apart:

gate.ensure_not_locked(email, ip)          # before the password is even tried
... entrance checks the password; on a wrong password it calls gate.password_failed(email, ip) ...
gate.second_factor(email, ip, user, code)  # after the password is right: code, enrolment rule, lockout counting
"""

from apps.core.utils import client_ip

from . import lockout, service


class Refused(Exception):
    """A sign-in was refused. `code` is machine-readable, `message` is for the person."""

    def __init__(self, code, message, status=403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def ip_of(request):
    return client_ip(request) if request is not None else ""


def ensure_not_locked(email, ip):
    if lockout.is_locked(email, ip):
        raise Refused("locked", lockout.LOCK_MESSAGE, 429)


def password_failed(email, ip):
    lockout.register_failure(email, ip)


def second_factor(email, ip, user, code):
    """Raise Refused unless this user may be signed in. A wrong code counts for the lockout, a missing one does not.

    Returns True when a second factor was actually proven (the API puts that in the token), False when none was asked.
    """
    if service.enrollment_required(user):
        raise Refused(
            "mfa_enrollment_required",
            "Two-step verification is required for team accounts. Set it up at /account/mfa/enroll/ first.",
        )
    proven = False
    if service.second_factor_needed(user):
        if not (code or "").strip():
            raise Refused(
                "mfa_required", "Enter the verification code from your authenticator app, or a recovery code."
            )
        if not service.verify_second_factor(user, code):
            lockout.register_failure(email, ip)
            ensure_not_locked(email, ip)
            raise Refused("mfa_invalid", "That verification code is not valid.", 401)
        proven = True
    lockout.reset(email, ip)
    return proven
