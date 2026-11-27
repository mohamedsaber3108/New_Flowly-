"""Shared Django settings for Flowly. Environment-specific files extend this."""

from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config

from config.unfold import UNFOLD  # noqa: F401  (Unfold reads this name from settings)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
ADMIN_URL = config("ADMIN_URL", default="admin/").strip("/") + "/"

SITE_ID = 1

INSTALLED_APPS = [
    "unfold",  # must come before django.contrib.admin
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # project apps
    "apps.core",
    "apps.accounts",
    "apps.leads",
    "apps.security",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.security.middleware.StaffSessionLimitsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.audit.context.AuditContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        config("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=60,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# Both hashers are always listed, so an Argon2 hash and a PBKDF2 hash both verify. The FIRST one is used for new
# hashes and decides what gets upgraded at login:
#   PASSWORD_HASH_ARGON2=False (default): PBKDF2 first. New hashes stay PBKDF2, nothing is upgraded. Safe to roll back.
#   PASSWORD_HASH_ARGON2=True: Argon2 first. Each user's hash is upgraded to Argon2 the next time they sign in.
# Once it has been True, roll back only to a commit that still lists Argon2 (see the FL-20 runbook in the PR).
PASSWORD_HASH_ARGON2 = config("PASSWORD_HASH_ARGON2", default=False, cast=bool)


def build_password_hashers(argon2_first):
    argon2 = "django.contrib.auth.hashers.Argon2PasswordHasher"
    pbkdf2 = "django.contrib.auth.hashers.PBKDF2PasswordHasher"
    return [argon2, pbkdf2] if argon2_first else [pbkdf2, argon2]


PASSWORD_HASHERS = build_password_hashers(PASSWORD_HASH_ARGON2)

# Email verification is enforced at login by the API. Set to False only for demos.
# Defaults to ON only when SMTP credentials are configured: without a mail server nobody could ever verify,
# which would make sign-up unusable. Unverified accounts never see anonymous requests sharing their email.
REQUIRE_EMAIL_VERIFICATION = config(
    "REQUIRE_EMAIL_VERIFICATION", default=bool(config("EMAIL_HOST_USER", default="")), cast=bool
)

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory" if REQUIRE_EMAIL_VERIFICATION else "optional"
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": config("GOOGLE_CLIENT_ID", default=""),
            "secret": config("GOOGLE_CLIENT_SECRET", default=""),
            "key": "",
        },
    }
}
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET", default="")

LOGIN_URL = "/account/"

# --- URLs / frontend --------------------------------------------------------
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000").rstrip("/")
# Public origin of this Django site (used in emailed links and Google callback).
SITE_URL = config("SITE_URL", default="http://localhost:8000").rstrip("/")
PUBLIC_ORIGIN = config("PUBLIC_ORIGIN", default="").rstrip("/")
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS = False
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# --- REST framework ---------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.session_cookie.CookieJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["apps.core.renderers.EnvelopeJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.envelope_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "NUM_PROXIES": config("NUM_PROXIES", default=0, cast=int),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="1000/hour"),
        "user": config("THROTTLE_USER", default="5000/hour"),
        # Public intake (mirrors the original frontend limits)
        "request": config("THROTTLE_REQUEST", default="8/hour"),
        "lookup": config("THROTTLE_LOOKUP", default="20/hour"),
        "assistant": config("THROTTLE_ASSISTANT", default="30/hour"),
        # Auth endpoints
        "auth_login": config("THROTTLE_LOGIN", default="10/min"),
        "auth_register": config("THROTTLE_REGISTER", default="10/hour"),
        "auth_reset": config("THROTTLE_RESET", default="5/hour"),
    },
}

# Staff sign-in cookies (FL-22). Staff tokens live in httpOnly cookies; a bearer header for a staff account is
# refused unless this is on (for a script or tool that cannot use a browser session). Customers are not affected.
ALLOW_STAFF_BEARER = config("ALLOW_STAFF_BEARER", default=False, cast=bool)
STAFF_COOKIE_SECURE = config("STAFF_COOKIE_SECURE", default=True, cast=bool)  # False only for http://localhost
STAFF_SESSION_IDLE_SECONDS = config("STAFF_SESSION_IDLE_SECONDS", default=1800, cast=int)  # refresh cookie life
CSRF_COOKIE_SAMESITE = "Strict"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Flowly API",
    "DESCRIPTION": (
        "Backend for the Flowly services website: lead intake, consultation "
        "scheduling, request tracking, team operations, assistant and user accounts. "
        "Routes under /api/v1/ return {success, data, message, errors}. Routes under "
        "/api/ (no version) are the original frontend contract and return raw JSON."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "RequestStatusEnum": "apps.leads.models.RequestStatus",
        "AppointmentStatusEnum": "apps.leads.models.AppointmentStatus",
        "RoleEnum": "apps.accounts.models.UserRole",
    },
}

# --- Cache (shared across Gunicorn workers; used by throttling) -------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "flowly_cache_table",
        # Django's default is 300 entries. When the table is full it deletes the lowest KEYS first (not the oldest),
        # and every visitor's throttle key adds a row, so counters such as "assistant:model-calls:<day>" and the
        # sign-in lock counters could be thrown away early and a cap would reset. 50000 rows is a few MB; when it is
        # ever full, only 1 row in 10 is culled.
        "OPTIONS": {"MAX_ENTRIES": 50000, "CULL_FREQUENCY": 10},
    }
}

# --- Flowly business settings ----------------------------------------------
ADMIN_TOKEN = config("ADMIN_TOKEN", default="")  # legacy /team bearer token (>= 32 chars)
# Where `manage.py export_audit_log` writes its daily JSONL + SHA-256 files (a folder on the app server).
AUDIT_EXPORT_DIR = config("AUDIT_EXPORT_DIR", default=str(BASE_DIR / "audit_exports"))
# The shared ADMIN_TOKEN is ignored (401) unless this is True. Default off: team members sign in with a named account.
ALLOW_SHARED_ADMIN_TOKEN = config("ALLOW_SHARED_ADMIN_TOKEN", default=False, cast=bool)

# --- Staff sign-in hardening (FL-09) ---------------------------------------
# Owner/staff must prove a second factor (authenticator code or recovery code) at every sign-in entrance. Default
# off, so deploying does not lock the team out: enrol everyone first (/account/mfa/enroll/), then set this to True.
# People who already enrolled are asked for a code even while this is off.
REQUIRE_STAFF_MFA = config("REQUIRE_STAFF_MFA", default=False, cast=bool)
# Fernet key that encrypts the authenticator secrets in the database. Generate it on the server and keep it in .env:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MFA_ENCRYPTION_KEY = config("MFA_ENCRYPTION_KEY", default="")
# 5 failed sign-ins within 15 minutes lock that account's sign-in for 15 minutes, on every entrance.
LOGIN_LOCKOUT_ATTEMPTS = config("LOGIN_LOCKOUT_ATTEMPTS", default=5, cast=int)
LOGIN_LOCKOUT_SECONDS = config("LOGIN_LOCKOUT_SECONDS", default=900, cast=int)
# ... per email AND per IP address (5), plus a cap per IP across all emails (20) and one per email across all IPs (50).
LOGIN_LOCKOUT_IP_ATTEMPTS = config("LOGIN_LOCKOUT_IP_ATTEMPTS", default=20, cast=int)
LOGIN_LOCKOUT_EMAIL_ATTEMPTS = config("LOGIN_LOCKOUT_EMAIL_ATTEMPTS", default=50, cast=int)
# Django admin sessions of staff: signed out after 30 minutes without a request, and after 8 hours in all.
ADMIN_SESSION_IDLE_SECONDS = config("ADMIN_SESSION_IDLE_SECONDS", default=1800, cast=int)
ADMIN_SESSION_MAX_SECONDS = config("ADMIN_SESSION_MAX_SECONDS", default=28800, cast=int)
TEAM_NOTIFY_EMAIL = config("TEAM_NOTIFY_EMAIL", default="")
ASSISTANT_LOG_ENABLED = config("ASSISTANT_LOG_ENABLED", default=False, cast=bool)
# Kill switch: the assistant uses an AI model ONLY when this is True AND a provider is configured. Default off, so the
# catalog guide answers (no provider cost, no model risk) until the owner switches it on (FL-17).
ASSISTANT_AI_ENABLED = config("ASSISTANT_AI_ENABLED", default=False, cast=bool)
# Most model calls per day (Africa/Cairo day) across the whole site. Over the limit, visitors get the guide.
ASSISTANT_DAILY_LIMIT = config("ASSISTANT_DAILY_LIMIT", default=200, cast=int)
AI_PROVIDER = config("AI_PROVIDER", default="")  # bedrock | compatible | dify | "" (guide only)
AI_API_URL = config("AI_API_URL", default="")
AI_API_KEY = config("AI_API_KEY", default="")
AI_MODEL = config("AI_MODEL", default="")
DIFY_API_URL = config("DIFY_API_URL", default="")
DIFY_API_KEY = config("DIFY_API_KEY", default="")
BEDROCK_MODEL_ID = config("BEDROCK_MODEL_ID", default="")
AWS_REGION = config("AWS_REGION", default="us-east-1")

# --- i18n -------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Cairo"
USE_I18N = True
USE_TZ = True

# --- Static & media ---------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(config("MEDIA_ROOT", default=str(BASE_DIR / "media")))
MAX_UPLOAD_SIZE_MB = config("MAX_UPLOAD_SIZE_MB", default=10, cast=int)
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# --- Email ------------------------------------------------------------------
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Flowly <noreply@localhost>")

# --- Logging ----------------------------------------------------------------
LOG_DIR = Path(config("LOG_DIR", default=str(BASE_DIR / "logs")))
LOG_TO_FILE = config("LOG_TO_FILE", default=True, cast=bool)
try:
    if LOG_TO_FILE:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:  # read-only location: fall back to console only
    LOG_TO_FILE = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        **(
            {
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": str(LOG_DIR / "flowly.log"),
                    "maxBytes": 5 * 1024 * 1024,
                    "backupCount": 5,
                    "formatter": "standard",
                }
            }
            if LOG_TO_FILE
            else {}
        ),
    },
    "root": {"handlers": ["console"] + (["file"] if LOG_TO_FILE else []), "level": "INFO"},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "apps": {"level": "INFO"},
    },
}
