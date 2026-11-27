from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.audit import service as audit
from apps.security import lockout
from apps.security import service as mfa_service

from .models import User

# Fields whose change gives or removes access. Any change is audited, fail closed.
ACCESS_FIELDS = ("role", "status", "is_active", "is_staff", "is_superuser", "is_deleted")


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

    def has_delete_permission(self, request, obj=None):
        """No hard delete of users in the admin, for anyone (superusers too). Reason: a hard delete cascades and
        cannot be audited reliably, and the soft delete (`is_deleted`, audited in save_model below) keeps the row
        for request history. This also removes the "Delete selected users" bulk action."""
        return False

    def save_model(self, request, obj, form, change):
        """Audit role, status and access changes. Django wraps the admin save in a transaction, and the entry is
        sensitive (fail closed), so if the audit write fails the change is rolled back.
        shortcut: the admin form has no reason field yet; the reason says where the change came from."""
        before = {}
        if change:
            stored = User.objects.get(pk=obj.pk)
            before = {f: getattr(stored, f) for f in ACCESS_FIELDS}
        after = {f: getattr(obj, f) for f in ACCESS_FIELDS}
        changed = {f for f in ACCESS_FIELDS if before.get(f) != after[f]} if change else set()
        super().save_model(request, obj, form, change)
        if not change:
            if obj.role != User.Role.CUSTOMER or obj.is_staff or obj.is_superuser:
                audit.record(
                    audit.A.USER_CREATE,
                    actor=request.user,
                    target=obj,
                    after=after,
                    reason="Created in Django admin",
                    sensitive=True,
                )
            return
        groups = []  # (action, fields): a role change and a suspension in one save are two entries
        if changed & {"role", "is_staff", "is_superuser"}:
            groups.append((audit.A.USER_ROLE, changed & {"role", "is_staff", "is_superuser"}))
        if "is_deleted" in changed and obj.is_deleted:  # soft delete by ticking the box in the admin form
            groups.append((audit.A.USER_DELETE, {"is_deleted", "is_active"}))
        elif changed & {"status", "is_active"}:
            reactivated = obj.is_active and obj.status == User.Status.ACTIVE
            groups.append(
                (audit.A.USER_REACTIVATE if reactivated else audit.A.USER_SUSPEND, changed & {"status", "is_active"})
            )
        for action, fields in groups:
            audit.record(
                action,
                actor=request.user,
                target=obj,
                before={f: before[f] for f in fields},
                after={f: after[f] for f in fields},
                reason="Changed in Django admin",
                sensitive=True,
            )
