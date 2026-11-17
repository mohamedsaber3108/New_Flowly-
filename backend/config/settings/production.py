from decouple import Csv, config

from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, DATABASES, SECRET_KEY

DEBUG = False  # enforced: never overridable from the environment


if SECRET_KEY == "insecure-dev-key-change-me" or len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be set to a unique value of at least 32 characters.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must list explicit hostnames in production.")
if DATABASES["default"]["ENGINE"].endswith("sqlite3") and not config(
    "ALLOW_SQLITE_IN_PRODUCTION", default=False, cast=bool
):
    raise RuntimeError("Production requires PostgreSQL: set DATABASE_URL=postgres://...")

# Local health checks (deploy scripts, monitoring) call Gunicorn on loopback.
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ["127.0.0.1", "localhost"]

# SMTP when credentials exist; otherwise emails are written to the application log (never silently lost,
# and no connection errors) until SMTP is configured.
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend"
        if config("EMAIL_HOST_USER", default="")
        else "django.core.mail.backends.console.EmailBackend"
    ),
)

# TLS terminates at Nginx, which sets X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
# Behind Nginx: trust exactly one proxy for client IP (throttling).
REST_FRAMEWORK["NUM_PROXIES"] = config("NUM_PROXIES", default=1, cast=int)  # noqa: F405
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default=config("FRONTEND_URL", default=""), cast=Csv())
