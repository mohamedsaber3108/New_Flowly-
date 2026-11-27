import csv
import json

from django.contrib import admin, messages
from django.http import HttpResponse
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.admin import TabularInline as UnfoldTabularInline
from unfold.decorators import action

from apps.audit import service as audit

from . import services
from .models import Appointment, AssistantMessage, Request, RequestEvent


def _csv_safe(value):
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class AppointmentInline(UnfoldTabularInline):
    model = Appointment
    extra = 0
    fields = ["date", "time", "timezone", "status"]
    readonly_fields = ["date", "time", "timezone"]
    can_delete = False
    show_change_link = True


class RequestEventInline(UnfoldTabularInline):
    model = RequestEvent
    extra = 0
    fields = ["created_at", "event_type", "status", "actor"]
    readonly_fields = ["created_at", "event_type", "status", "actor"]
    can_delete = False
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None):
        return False


def _set_status(modeladmin, request, queryset, status):
    changed = 0
    for req in queryset.prefetch_related("appointments"):
        try:
            services.update_request(req, status=status, actor=request.user)
            changed += 1
        except services.SlotTaken:
            messages.error(request, f"{req.reference}: that consultation slot is already booked by someone else.")
    messages.success(request, f"{changed} request(s) set to {status.replace('_', ' ')}.")


@admin.register(Request)
class RequestAdmin(UnfoldModelAdmin):
    list_display = ["reference", "name", "organization", "kind", "audience", "status", "assigned_to", "created_at"]
    list_filter = ["status", "kind", "audience", "language", "created_at"]
    search_fields = ["reference", "name", "email", "organization"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id",
        "uuid",
        "reference",
        "details_pretty",
        "consent",
        "user",
        "created_at",
        "updated_at",
        "reviewed_at",
    ]
    exclude = ["details"]
    list_select_related = ["assigned_to"]
    compressed_fields = True
    warn_unsaved_form = True
    list_filter_submit = True
    inlines = [AppointmentInline, RequestEventInline]
    actions = ["export_csv", "mark_in_review", "mark_confirmed", "mark_declined"]
    actions_row = []

    @admin.display(description="Submitted details")
    def details_pretty(self, obj):
        from django.utils.html import format_html

        return format_html(
            "<pre style='white-space:pre-wrap'>{}</pre>", json.dumps(obj.details, indent=2, ensure_ascii=False)
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_to":  # only active team members can own a request
            from apps.accounts.models import User

            kwargs["queryset"] = User.objects.filter(
                role__in=["owner", "staff"], is_active=True, is_deleted=False
            ).order_by("email")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Status, note and assignee edits go through services.update_request, exactly like the /team console
        and the API: appointments follow the status, the customer is emailed, events record the admin."""
        tracked = {"status", "internal_note", "assigned_to"}
        if not change or not tracked & set(form.changed_data):
            super().save_model(request, obj, form, change)
            return
        stored = Request.objects.get(pk=obj.pk)
        wanted = {f: getattr(obj, f) for f in tracked}
        for f in tracked:  # save other edited fields first, without the tracked ones
            setattr(obj, f, getattr(stored, f))
        super().save_model(request, obj, form, change)
        try:
            services.update_request(
                obj,
                status=wanted["status"] if "status" in form.changed_data else None,
                internal_note=wanted["internal_note"] if "internal_note" in form.changed_data else None,
                assigned_to=wanted["assigned_to"],
                assign="assigned_to" in form.changed_data,
                actor=request.user,
            )
        except services.SlotTaken:
            messages.error(
                request,
                f"{obj.reference}: status not changed. Its consultation slot is now held by another request.",
            )

    @action(description="Export selected as CSV")
    def export_csv(self, request, queryset):
        # Fail closed: the audit entry is written first. If it cannot be written, no data leaves.
        audit.record(
            audit.A.EXPORT_REQUESTS,
            actor=request.user,
            target_type="request",
            target_id="bulk",
            after={"count": queryset.count(), "filename": "Flowly-requests.csv"},
            reason="Export from Django admin",
            sensitive=True,
        )
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="Flowly-requests.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(
            [
                "reference",
                "created_at",
                "kind",
                "audience",
                "name",
                "email",
                "organization",
                "status",
                "date",
                "time",
                "requirements",
                "internal_note",
            ]
        )
        for req in queryset.prefetch_related("appointments"):
            appointment = req.appointments.order_by("-pk").first()
            writer.writerow(
                [
                    _csv_safe(v)
                    for v in [
                        req.reference,
                        req.created_at.isoformat(),
                        req.kind,
                        req.audience,
                        req.name,
                        req.email,
                        req.organization,
                        req.status,
                        appointment.date if appointment else "",
                        appointment.time if appointment else "",
                        req.details.get("requirements", ""),
                        req.internal_note,
                    ]
                ]
            )
        return response

    @action(description="Mark as in review")
    def mark_in_review(self, request, queryset):
        _set_status(self, request, queryset, "in_review")

    @action(description="Mark as confirmed")
    def mark_confirmed(self, request, queryset):
        _set_status(self, request, queryset, "confirmed")

    @action(description="Mark as declined")
    def mark_declined(self, request, queryset):
        _set_status(self, request, queryset, "declined")


@admin.register(Appointment)
class AppointmentAdmin(UnfoldModelAdmin):
    list_display = ["slot", "request", "status", "timezone", "created_at"]
    list_filter = ["status", "date"]
    search_fields = ["request__reference", "request__name", "request__email", "slot"]
    ordering = ["-date", "-time"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    list_select_related = ["request"]
    compressed_fields = True
    warn_unsaved_form = True


@admin.register(RequestEvent)
class RequestEventAdmin(UnfoldModelAdmin):
    list_display = ["request", "event_type", "status", "actor", "created_at"]
    list_filter = ["event_type", "status"]
    search_fields = ["request__reference", "request__email"]
    ordering = ["-created_at"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    list_select_related = ["request", "actor"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AssistantMessage)
class AssistantMessageAdmin(UnfoldModelAdmin):
    list_display = ["short_message", "language", "mode", "user", "created_at"]
    list_filter = ["mode", "language"]
    search_fields = ["message", "reply"]
    ordering = ["-created_at"]
    readonly_fields = ["uuid", "created_at", "updated_at"]
    list_select_related = ["user"]

    @admin.display(description="Message")
    def short_message(self, obj):
        return obj.message[:80]


from . import settings_admin  # noqa: E402,F401  (registers the site settings and blocked-day pages)
