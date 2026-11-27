"""Admin pages for the site settings, the blocked days and the read-only module registry (FL-21).

Who may do what (checked on the server, not only in the page):
* owner (and superuser): view and change the settings, add and remove blocked days;
* staff and viewer: view only (the page shows the values, the save buttons are not offered and a POST is refused);
* everyone else: no access.
Every change writes one JSON line to the logger "flowly.admin" (who, what, before and after).
No setting here is a secret.
"""

import re

from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from apps.core.adminlog import log_admin_event
from apps.core.modules import registry

from . import site_settings
from .models import BlockedDay, SiteSettings

WEEKDAY_CHOICES = [  # Sunday first: the working week here starts on Sunday
    (6, "Sunday"),
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
]
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# Default taken (question Q-F14, ADMIN.md s.3: settings and flags are changed by the top role only): owner and
# superuser change; staff and viewer read. The owner may widen this to owner + staff by adding "staff" here.
CHANGE_ROLES = ("owner",)
VIEW_ROLES = ("owner", "staff", "viewer")


def can_view(request):
    user = request.user
    return bool(user.is_active and (user.is_superuser or getattr(user, "role", "") in VIEW_ROLES))


def can_change(request):
    user = request.user
    return bool(user.is_active and (user.is_superuser or getattr(user, "role", "") in CHANGE_ROLES))


class SiteSettingsForm(forms.ModelForm):
    booking_weekdays = forms.TypedMultipleChoiceField(
        label="Booking days",
        choices=WEEKDAY_CHOICES,
        coerce=int,
        required=False,  # an empty choice reaches clean_booking_weekdays, which gives the clear message
        widget=forms.CheckboxSelectMultiple,
        help_text="Days of the week when a consultation can be requested. Today: Sunday to Thursday.",
    )
    slot_times = forms.CharField(
        label="Time slots (Africa/Cairo time)",
        help_text="24-hour times separated by commas, for example: 10:00, 11:00, 12:00, 14:00, 15:00.",
        widget=forms.TextInput(attrs={"size": 60}),
    )
    booking_horizon_days = forms.IntegerField(
        label="How far ahead (days)", min_value=1, max_value=365, help_text="From 1 to 365. Today: 90."
    )

    class Meta:
        model = SiteSettings
        fields = ["assistant_enabled", "intake_enabled", "booking_weekdays", "slot_times", "booking_horizon_days"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["booking_weekdays"] = list(self.instance.booking_weekdays)
            self.initial["slot_times"] = ", ".join(self.instance.slot_times)

    def clean_slot_times(self):
        parts = [p.strip() for p in re.split(r"[,\s;]+", self.cleaned_data["slot_times"]) if p.strip()]
        bad = [p for p in parts if not TIME_RE.match(p)]
        if bad:
            raise forms.ValidationError(f"Use the form HH:MM (for example 14:30). Not valid: {', '.join(bad)}.")
        times = sorted(set(parts))
        if not times:
            raise forms.ValidationError("Give at least one time.")
        if len(times) > 24:
            raise forms.ValidationError("At most 24 time slots.")
        return times

    def clean_booking_weekdays(self):
        days = sorted(set(self.cleaned_data["booking_weekdays"]))
        if not days:
            raise forms.ValidationError("Choose at least one day (or switch new requests off).")
        return days


@admin.register(SiteSettings)
class SiteSettingsAdmin(UnfoldModelAdmin):
    form = SiteSettingsForm
    fieldsets = (
        ("Switches", {"fields": ("assistant_enabled", "intake_enabled")}),
        ("Consultation booking", {"fields": ("booking_weekdays", "slot_times", "booking_horizon_days")}),
        ("Modules (read-only)", {"fields": ("module_registry",)}),
        ("Last change", {"fields": ("updated_at", "updated_by")}),
    )
    readonly_fields = ["module_registry", "updated_at", "updated_by"]
    compressed_fields = True
    warn_unsaved_form = True

    # --- who may do what -----------------------------------------------------------------------------------------
    def has_module_permission(self, request):
        return can_view(request)

    def has_view_permission(self, request, obj=None):
        return can_view(request)

    def has_change_permission(self, request, obj=None):
        return can_change(request)

    def has_add_permission(self, request):
        return False  # the single row is created on first visit

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        """There is one row: go straight to it."""
        if not can_view(request):
            return super().changelist_view(request, extra_context)
        SiteSettings.load()
        return redirect(reverse("admin:leads_sitesettings_change", args=[1]))

    # --- module registry -----------------------------------------------------------------------------------------
    @admin.display(description="Module registry")
    def module_registry(self, obj):
        rows = registry(site_settings.get())
        body = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
            (
                (
                    r["id"],
                    f"{r['name']}",
                    r["roles"],
                    f"{'OK' if r['healthy'] else 'FAILED'}: {r['detail']}",
                    "On" if r["enabled"] else "Off",
                )
                for r in rows
            ),
        )
        return format_html(
            '<table><caption class="sr-only">Modules</caption>'
            '<thead><tr><th scope="col">Id</th><th scope="col">Name</th><th scope="col">Who uses it</th>'
            '<th scope="col">Backend health</th><th scope="col">Switch</th></tr></thead><tbody>{}</tbody></table>',
            body,
        )

    # --- saving, with a log line ---------------------------------------------------------------------------------
    def save_model(self, request, obj, form, change):
        if not can_change(request):  # defence in depth: has_change_permission already refuses
            raise PermissionError("not allowed")
        before = {f: getattr(SiteSettings.load(), f) for f in form.fields}
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        changes = {f: [before[f], getattr(obj, f)] for f in form.fields if before[f] != getattr(obj, f)}
        if changes:
            log_admin_event("settings.changed", request.user, changes=changes)


@admin.register(BlockedDay)
class BlockedDayAdmin(UnfoldModelAdmin):
    list_display = ["date", "weekday", "reason", "created_at"]
    search_fields = ["reason"]
    ordering = ["date"]
    date_hierarchy = "date"

    @admin.display(description="Day")
    def weekday(self, obj):
        return obj.date.strftime("%A")

    def has_module_permission(self, request):
        return can_view(request)

    def has_view_permission(self, request, obj=None):
        return can_view(request)

    def has_change_permission(self, request, obj=None):
        return can_change(request)

    def has_add_permission(self, request):
        return can_change(request)

    def has_delete_permission(self, request, obj=None):
        return can_change(request)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_admin_event(
            "blocked_day.changed" if change else "blocked_day.added",
            request.user,
            date=obj.date.isoformat(),
            reason=obj.reason,
        )

    def delete_model(self, request, obj):
        date = obj.date.isoformat()
        super().delete_model(request, obj)
        log_admin_event("blocked_day.removed", request.user, date=date)

    def delete_queryset(self, request, queryset):
        dates = [d.isoformat() for d in queryset.values_list("date", flat=True)]
        super().delete_queryset(request, queryset)
        for date in dates:
            log_admin_event("blocked_day.removed", request.user, date=date)
