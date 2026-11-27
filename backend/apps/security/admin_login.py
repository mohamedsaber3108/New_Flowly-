"""Entrance 1: the Django admin sign-in page. Adds the verification-code field and the lockout."""

from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError

from . import gate


class StaffAdminAuthenticationForm(AdminAuthenticationForm):
    otp = forms.CharField(
        label="Verification code (staff with two-step verification: authenticator code or recovery code)",
        required=False,
        strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "text"}),  # paste is allowed
    )

    def clean(self):
        email = (self.data.get("username") or "").strip().lower()
        try:
            gate.ensure_not_locked(email)
        except gate.Refused as refused:
            raise ValidationError(refused.message, code=refused.code)
        try:
            cleaned = super().clean()  # checks the password and that the account may use the admin
        except ValidationError:
            gate.password_failed(email)
            raise
        user = self.get_user()
        if user is not None:
            try:
                gate.second_factor(email, user, self.cleaned_data.get("otp", ""))
            except gate.Refused as refused:
                self.user_cache = None
                raise ValidationError(refused.message, code=refused.code)
        return cleaned
