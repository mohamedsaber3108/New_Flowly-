from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.security import lockout
from apps.security import service as mfa_service

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin, UnfoldModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    model = User

    actions = ["reset_two_step_verification", "clear_sign_in_lock"]

    @admin.action(description="Clear sign-in lock (after too many failed attempts)")
    def clear_sign_in_lock(self, request, queryset):
        """An owner lifts the 15-minute lock on an account at once, for every address. Logged."""
        if not (request.user.is_superuser or getattr(request.user, "role", "") == "owner"):
            self.message_user(request, "Only an owner can clear a sign-in lock.", level="error")
            return
        for user in queryset:
            lockout.clear_email(user.email, by=f"{request.user.email} (admin action)")
        self.message_user(request, f"Sign-in lock cleared for {queryset.count()} user(s).")

    @admin.action(description="Reset two-step verification (the person sets it up again)")
    def reset_two_step_verification(self, request, queryset):
        """Lost phone and recovery codes: an owner removes the device so the person can enrol again."""
        if not (request.user.is_superuser or getattr(request.user, "role", "") == "owner"):
            self.message_user(request, "Only an owner can reset two-step verification.", level="error")
            return
        for user in queryset:
            mfa_service.reset_device(user, by=f"{request.user.email} (admin action)")
        self.message_user(request, f"Two-step verification reset for {queryset.count()} user(s).")

    list_display = ["email", "full_name", "role", "status", "is_active", "is_deleted", "created_at"]
    list_filter = ["role", "status", "is_active", "is_deleted", "is_staff"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-created_at"]
    readonly_fields = ["uuid", "created_at", "updated_at", "last_login", "date_joined", "deleted_at"]
    compressed_fields = True
    warn_unsaved_form = True

    fieldsets = (
        (None, {"fields": ("uuid", "email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "avatar")}),
        (
            "Access",
            {"fields": ("role", "status", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Deletion", {"fields": ("is_deleted", "deleted_at")}),
        ("Dates", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "role", "password1", "password2")},
        ),
    )
