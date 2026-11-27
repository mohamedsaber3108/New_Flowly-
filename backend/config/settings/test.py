from cryptography.fernet import Fernet

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production-0123456789"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_ROOT = BASE_DIR / "media_test"  # noqa: F405
LOG_TO_FILE = False
REQUIRE_EMAIL_VERIFICATION = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ADMIN_TOKEN = "flowly-local-test-admin-token-123456789"
MFA_ENCRYPTION_KEY = Fernet.generate_key().decode()  # a new throwaway key each test run: nothing is stored or reused
FRONTEND_URL = "https://flowly.test"
SITE_URL = "https://flowly.test"
REST_FRAMEWORK["NUM_PROXIES"] = 0  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # noqa: F405
    "anon": "100000/hour",
    "user": "100000/hour",
    "auth_login": "100/min",
    "auth_register": "100/hour",
    "auth_reset": "100/hour",
}
GOOGLE_CLIENT_ID = "test-google-client-id"
GOOGLE_CLIENT_SECRET = "test-google-client-secret"
