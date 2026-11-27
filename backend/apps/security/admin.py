from django.contrib import admin
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .models import MfaDevice


@admin.register(MfaDevice)
class MfaDeviceAdmin(UnfoldModelAdmin):
    """Who has two-step verification (read-only). The owner checks this list before switching REQUIRE_STAFF_MFA on.
    The secret is never shown. To let someone enrol again use the user list action "Reset two-step verification"."""

    list_display = ["user", "enrolled", "confirmed_at", "created_at"]
    list_filter = ["confirmed_at"]
    search_fields = ["user__email"]
    fields = ["user", "enrolled", "confirmed_at", "created_at"]
    readonly_fields = fields

    @admin.display(boolean=True, description="Enrolled (confirmed)")
    def enrolled(self, obj):
        return obj.confirmed_at is not None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
