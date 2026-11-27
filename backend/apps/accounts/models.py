import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.OWNER)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)


def avatar_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"avatars/{instance.uuid}.{ext}"


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        STAFF = "staff", "Staff"
        VIEWER = "viewer", "Viewer (read-only team)"
        CUSTOMER = "customer", "Customer"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    username = None
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField("email address", unique=True)
    avatar = models.ImageField(upload_to=avatar_path, blank=True, null=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        db_table = "accounts_users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_team(self):
        return self.is_superuser or self.role in (self.Role.OWNER, self.Role.STAFF, self.Role.VIEWER)

    def has_perm(self, perm, obj=None):
        """A viewer is read-only in the Django admin whatever groups or permissions someone gives them (ADMIN.md s.3:
        viewer = Analyst). Django asks this for every add, change and delete in the admin, so the refusal is on the
        server and does not depend on a page hiding a button. Viewing is left to the normal rules."""
        if self.role == self.Role.VIEWER and not self.is_superuser:
            if perm.rsplit(".", 1)[-1].split("_", 1)[0] in ("add", "change", "delete"):
                return False
        return super().has_perm(perm, obj)

    def soft_delete(self, actor=None, reason="Account deleted"):
        """Never hard-delete: disable login, keep the row for audit and request history.

        Fail closed: the audit entry is written in the same transaction, so no audit means no deletion.
        `actor` is the person who asked (the user themselves for self-service deletion, if not given)."""
        from django.db import transaction

        from apps.audit import service as audit

        with transaction.atomic():
            audit.record(
                audit.A.USER_DELETE,
                actor=actor or self,
                target=self,
                before={"is_deleted": False, "is_active": self.is_active, "role": self.role},
                after={"is_deleted": True, "is_active": False},
                reason=reason,
                sensitive=True,
            )
            self.is_deleted = True
            self.is_active = False
            self.deleted_at = timezone.now()
            self.save(update_fields=["is_deleted", "is_active", "deleted_at", "updated_at"])


# Module-level alias used by drf-spectacular ENUM_NAME_OVERRIDES.
UserRole = User.Role
