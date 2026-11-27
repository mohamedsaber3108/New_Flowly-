import json
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.contrib.filters.admin import FieldTextFilter, RangeDateTimeFilter

from .models import AuditEntry

CAIRO = ZoneInfo("Africa/Cairo")


@admin.register(AuditEntry)
class AuditEntryAdmin(UnfoldModelAdmin):
    """Read-only for everyone, superusers included. The table itself is insert-only (see models.py)."""

    list_display = ["time_cairo", "actor_label", "actor_role", "action", "target_type", "target_id", "result", "ip"]
    list_filter = [
        ("actor_label", FieldTextFilter),
        "action",
        "result",
        ("time", RangeDateTimeFilter),
    ]
    list_filter_submit = True
    search_fields = ["actor_label", "target_id", "request_id", "ip"]
    ordering = ["-time", "-id"]
    list_per_page = 50
    date_hierarchy = None
    readonly_fields = [
        "time_cairo",
        "time",
        "actor_id",
        "actor_label",
        "actor_role",
        "action",
        "target_type",
        "target_id",
        "before_pretty",
        "after_pretty",
        "reason",
        "result",
        "ip",
        "user_agent",
        "request_id",
    ]
    fields = readonly_fields
    actions = None

    @admin.display(description="Time (Cairo) / الوقت (القاهرة)", ordering="time")
    def time_cairo(self, obj):
        return obj.time.astimezone(CAIRO).strftime("%Y-%m-%d %H:%M:%S")

    @admin.display(description="Before / قبل")
    def before_pretty(self, obj):
        return self._pretty(obj.before)

    @admin.display(description="After / بعد")
    def after_pretty(self, obj):
        return self._pretty(obj.after)

    @staticmethod
    def _pretty(value):
        if value is None:
            return "-"
        return format_html(
            "<pre style='white-space:pre-wrap'>{}</pre>", json.dumps(value, indent=2, ensure_ascii=False)
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return bool(
            request.user.is_active and (request.user.is_superuser or getattr(request.user, "role", "") == "owner")
        )

    def has_module_permission(self, request):
        return self.has_view_permission(request)
