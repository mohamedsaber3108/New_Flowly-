import pytest
from allauth.account.models import EmailAddress
from django.core.management import call_command

from apps.accounts.models import User
from apps.leads.models import Appointment, Request

pytestmark = pytest.mark.django_db


def test_seed_demo_creates_verified_superuser_once(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "boss@example.test")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Str0ng-Passw0rd!x")
    call_command("seed_demo")
    call_command("seed_demo")  # idempotent
    boss = User.objects.get(email="boss@example.test")
    assert boss.is_superuser and boss.is_staff and boss.role == "owner"
    assert boss.check_password("Str0ng-Passw0rd!x")
    assert EmailAddress.objects.filter(user=boss, verified=True).count() == 1
    assert User.objects.count() == 1


def test_seed_demo_refuses_without_password_outside_debug(monkeypatch, capsys):
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)
    call_command("seed_demo")
    assert User.objects.count() == 0


def test_seed_demo_staff_and_demo_requests(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "Str0ng-Passw0rd!x")
    monkeypatch.setenv("DEMO_STAFF_EMAIL", "crew@example.test")
    monkeypatch.setenv("DEMO_STAFF_PASSWORD", "Str0ng-Passw0rd!x")
    call_command("seed_demo", "--demo-data")
    call_command("seed_demo", "--demo-data")
    assert User.objects.get(email="crew@example.test").role == "staff"
    assert Request.objects.count() == 3
    assert Appointment.objects.filter(status="provisional").count() == 1
