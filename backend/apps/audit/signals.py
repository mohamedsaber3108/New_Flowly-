"""Sign-in successes and failures, from Django's own signals (Django admin login and the API login)."""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from . import service as audit


@receiver(user_login_failed)
def on_login_failed(sender, credentials=None, **kwargs):
    # Only the email/username that was tried is kept. The password in `credentials` is never read.
    credentials = credentials or {}
    tried = credentials.get("email") or credentials.get("username") or ""
    audit.record(
        audit.A.LOGIN_FAILED,
        target_type="login",
        after={"email": str(tried)[:254]},
        result=audit.R.FAILED,
    )


@receiver(user_logged_in)
def on_logged_in(sender, user=None, **kwargs):
    audit.record(audit.A.LOGIN, actor=user, target=user, after={"via": "django-session"})
