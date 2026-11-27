"""The one check every sign-in entrance calls, so they cannot drift apart:

gate.ensure_not_locked(email)            # before the password is even tried
... entrance checks the password; on a wrong password it calls gate.password_failed(email) ...
gate.second_factor(email, user, code)    # after the password is right: code, enrolment rule, lockout counting
"""

from . import lockout, service


class Refused(Exception):
    """A sign-in was refused. `code` is machine-readable, `message` is for the person."""

    def __init__(self, code, message, status=403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def ensure_not_locked(email):
    if lockout.is_locked(email):
        raise Refused("locked", lockout.LOCK_MESSAGE, 429)


def password_failed(email):
    lockout.register_failure(email)


def second_factor(email, user, code):
    """Raise Refused unless this user may be signed in. A wrong code counts for the lockout, a missing one does not."""
    if service.enrollment_required(user):
        raise Refused(
            "mfa_enrollment_required",
            "Two-step verification is required for team accounts. Set it up at /account/mfa/enroll/ first.",
        )
    if service.second_factor_needed(user):
        if not (code or "").strip():
            raise Refused(
                "mfa_required", "Enter the verification code from your authenticator app, or a recovery code."
            )
        if not service.verify_second_factor(user, code):
            lockout.register_failure(email)
            ensure_not_locked(email)
            raise Refused("mfa_invalid", "That verification code is not valid.", 401)
    lockout.reset(email)
