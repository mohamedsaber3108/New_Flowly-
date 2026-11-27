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
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]

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
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
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
    }
}

# --- Flowly business settings ----------------------------------------------
ADMIN_TOKEN = config("ADMIN_TOKEN", default="")  # legacy /team bearer token (>= 32 chars)
# Where `manage.py export_audit_log` writes its daily JSONL + SHA-256 files (a folder on the app server).
AUDIT_EXPORT_DIR = config("AUDIT_EXPORT_DIR", default=str(BASE_DIR / "audit_exports"))
# The shared ADMIN_TOKEN is ignored (401) unless this is True. Default off: team members sign in with a named account.
ALLOW_SHARED_ADMIN_TOKEN = config("ALLOW_SHARED_ADMIN_TOKEN", default=False, cast=bool)
TEAM_NOTIFY_EMAIL = config("TEAM_NOTIFY_EMAIL", default="")
ASSISTANT_LOG_ENABLED = config("ASSISTANT_LOG_ENABLED", default=False, cast=bool)
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
