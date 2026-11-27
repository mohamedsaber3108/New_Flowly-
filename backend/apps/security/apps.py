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
