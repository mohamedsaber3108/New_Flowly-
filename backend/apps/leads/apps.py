from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"

    def ready(self):
        from . import schema  # noqa: F401
        from . import site_settings  # noqa: F401  (registers the signals that clear the settings cache)
