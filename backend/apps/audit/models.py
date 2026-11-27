"""Append-only audit log (ADMIN_FOUNDATION s.7).

Insert-only in two places: here (the ORM refuses to update or delete a stored row) and in Postgres
(deploy/sql/audit_grants.sql removes UPDATE and DELETE from the application role). Either alone is not enough.
"""

from django.db import models
from django.utils import timezone


class AuditError(Exception):
    """Raised when code tries to change or delete an audit entry."""


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AuditError("Audit entries cannot be updated.")

    def delete(self):
        raise AuditError("Audit entries cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise AuditError("Audit entries cannot be updated.")


class AuditEntry(models.Model):
    class Action(models.TextChoices):
        LOGIN = "auth.login", "Sign-in / تسجيل الدخول"
        LOGIN_FAILED = "auth.login_failed", "Sign-in failed / فشل تسجيل الدخول"
        USER_CREATE = "user.create", "User created / إنشاء مستخدم"
        USER_ROLE = "user.role_change", "Role or access change / تغيير الدور أو الصلاحية"
        USER_SUSPEND = "user.suspend", "User suspended / إيقاف مستخدم"
        USER_REACTIVATE = "user.reactivate", "User reactivated / إعادة تفعيل مستخدم"
        USER_DELETE = "user.delete", "User deleted / حذف مستخدم"
        REQUEST_STATUS = "request.status_change", "Request status changed / تغيير حالة الطلب"
        REQUEST_ASSIGN = "request.assign", "Request assigned / إسناد الطلب"
        REQUEST_NOTE = "request.note", "Request note changed / تعديل ملاحظة الطلب"
        REQUEST_PIPELINE = "request.pipeline", "Quote, value or follow-up changed / تغيير العرض أو القيمة أو المتابعة"
        EXPORT_REQUESTS = "export.requests_csv", "Requests exported / تصدير الطلبات"
        EXPORT_AUDIT = "export.audit_log", "Audit log exported / تصدير سجل التدقيق"
        SETTINGS = "settings.change", "Setting changed / تغيير إعداد"
        DENIED = "access.denied", "Access denied / رفض الوصول"

    class Result(models.TextChoices):
        SUCCESS = "success", "Success / نجاح"
        DENIED = "denied", "Denied / مرفوض"
        FAILED = "failed", "Failed / فشل"

    time = models.DateTimeField("Time (UTC) / الوقت", default=timezone.now, db_index=True, editable=False)
    # No foreign key on purpose: the row must survive any change to the user table.
    actor_id = models.BigIntegerField("Actor id / المنفذ", null=True, blank=True, db_index=True)
    actor_label = models.CharField("Actor / المنفذ", max_length=254, blank=True)
    actor_role = models.CharField("Role then / الدور وقتها", max_length=20, blank=True)
    action = models.CharField("Action / الإجراء", max_length=40, choices=Action.choices, db_index=True)
    target_type = models.CharField("Target type / نوع الهدف", max_length=40, blank=True)
    target_id = models.CharField("Target id / معرف الهدف", max_length=64, blank=True, db_index=True)
    before = models.JSONField("Before / قبل", null=True, blank=True)
    after = models.JSONField("After / بعد", null=True, blank=True)
    reason = models.TextField("Reason / السبب", blank=True)
    result = models.CharField("Result / النتيجة", max_length=10, choices=Result.choices, default=Result.SUCCESS)
    ip = models.GenericIPAddressField("IP / عنوان IP", null=True, blank=True)
    user_agent = models.CharField("Client / العميل", max_length=300, blank=True)
    request_id = models.CharField("Request id / معرف الطلب", max_length=64, blank=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        db_table = "audit_entries"
        ordering = ["-time", "-id"]
        verbose_name = "Audit entry / سجل تدقيق"
        verbose_name_plural = "Audit log / سجل التدقيق"
        indexes = [models.Index(fields=["actor_id", "time"]), models.Index(fields=["action", "time"])]

    def __str__(self):
        return f"{self.time:%Y-%m-%d %H:%M:%S} {self.action} {self.result}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditError("Audit entries cannot be changed once written.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditError("Audit entries cannot be deleted.")
