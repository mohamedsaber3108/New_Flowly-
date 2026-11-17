import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.leads.models import Appointment, Request
from tests.factories import AppointmentFactory, RequestFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_create_user_normalises_email_and_hashes_password():
    user = User.objects.create_user(email="Person@Example.TEST", password="abc12345!x")
    assert user.email == "person@example.test"
    assert user.check_password("abc12345!x")
    assert user.password != "abc12345!x"
    assert user.role == "customer"
    assert isinstance(user.uuid, uuid.UUID)


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="x")


def test_email_is_unique():
    UserFactory(email="dup@example.test")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="dup@example.test", password="x")


def test_superuser_flags_and_owner_role():
    admin = User.objects.create_superuser(email="root@example.test", password="x")
    assert admin.is_staff and admin.is_superuser
    assert admin.role == "owner"


def test_superuser_rejects_non_staff():
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="bad@example.test", password="x", is_staff=False)


def test_soft_delete_keeps_row_and_disables_login():
    user = UserFactory()
    user.soft_delete()
    user.refresh_from_db()
    assert user.is_deleted and not user.is_active and user.deleted_at is not None
    assert User.objects.filter(pk=user.pk).exists()


def test_active_slot_is_unique_but_canceled_slot_is_reusable():
    first = AppointmentFactory(slot="2026-12-02T10:00", date="2026-12-02", time="10:00")
    with pytest.raises(IntegrityError), transaction.atomic():
        AppointmentFactory(slot="2026-12-02T10:00", date="2026-12-02", time="10:00")
    first.status = Appointment.Status.CANCELED
    first.save()
    AppointmentFactory(slot="2026-12-02T10:00", date="2026-12-02", time="10:00")


def test_request_reference_is_unique():
    RequestFactory(reference="FLW-20261104-AAAAAAAA")
    with pytest.raises(IntegrityError), transaction.atomic():
        RequestFactory(reference="FLW-20261104-AAAAAAAA")


def test_request_defaults_and_user_set_null_on_delete():
    owner = UserFactory()
    req = RequestFactory(user=owner)
    assert req.status == Request.Status.PENDING_REVIEW
    owner.delete()
    req.refresh_from_db()
    assert req.user is None
