from django.conf import settings
from django.db import models


class MfaDevice(models.Model):
    """A user's authenticator app (TOTP, RFC 6238). The secret is stored encrypted (Fernet, MFA_ENCRYPTION_KEY)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mfa_device")
    secret = models.TextField()  # encrypted, never the plain secret
    confirmed_at = models.DateTimeField(null=True, blank=True)  # empty until the first code is proven
    last_step = models.BigIntegerField(default=0)  # newest 30 s step already used: a code works only once
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_mfa_devices"

    def __str__(self):
        return f"MFA device of {self.user_id} ({'confirmed' if self.confirmed_at else 'pending'})"


class RecoveryCode(models.Model):
    """One of 10 single-use codes. Only an HMAC of the code is stored."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes")
    digest = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "security_recovery_codes"
