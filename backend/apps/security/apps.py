import logging

from django.apps import AppConfig
from django.core import checks


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.security"

    def ready(self):
        from django.contrib import admin

        from .admin_login import StaffAdminAuthenticationForm

        admin.site.login_form = StaffAdminAuthenticationForm  # the admin sign-in page asks for the code
        checks.register(check_mfa_settings)
        warn_if_shared_key_conflicts()


def warn_if_shared_key_conflicts():
    """Both switches on is a mistake worth a line in the log: the shared key is ignored while MFA is required."""
    from django.conf import settings

    from .events import log_event

    if settings.REQUIRE_STAFF_MFA and settings.ALLOW_SHARED_ADMIN_TOKEN:
        log_event(
            "config.conflict",
            level=logging.WARNING,
            detail="ALLOW_SHARED_ADMIN_TOKEN and REQUIRE_STAFF_MFA are both on: the shared admin key is refused.",
        )


def check_mfa_settings(app_configs, **kwargs):
    """Refuse to start with the rule on but no key to read the authenticator secrets."""
    from django.conf import settings

    if settings.REQUIRE_STAFF_MFA and not settings.MFA_ENCRYPTION_KEY:
        return [
            checks.Error(
                "REQUIRE_STAFF_MFA is True but MFA_ENCRYPTION_KEY is empty.",
                hint="Generate a key and put it in backend/.env (see .env.example).",
                id="security.E001",
            )
        ]
    return []
