from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
REQUIRE_EMAIL_VERIFICATION = config("REQUIRE_EMAIL_VERIFICATION", default=False, cast=bool)  # noqa: F405
ACCOUNT_EMAIL_VERIFICATION = "mandatory" if REQUIRE_EMAIL_VERIFICATION else "optional"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# The Vite dev server runs on :5173 and proxies /api to Django.
CORS_ALLOWED_ORIGINS = list(CORS_ALLOWED_ORIGINS) + [  # noqa: F405
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
