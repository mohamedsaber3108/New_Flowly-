import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from tests.factories import PASSWORD, OwnerFactory, StaffFactory, UserFactory


@pytest.fixture(autouse=True)
def _clear_cache(settings, tmp_path):
    cache.clear()
    settings.MEDIA_ROOT = tmp_path / "media"
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def staff(db):
    return StaffFactory()


@pytest.fixture
def owner(db):
    return OwnerFactory()


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def staff_client(staff):
    client = APIClient()
    client.force_authenticate(staff)
    return client


def future_workday(days=4):
    """A valid consultation date: Cairo time, Sun-Thu, within 90 days."""
    day = datetime.now(ZoneInfo("Africa/Cairo")).date() + timedelta(days=days)
    while day.weekday() in (4, 5):
        day += timedelta(days=1)
    return day.isoformat()


@pytest.fixture
def workday():
    return future_workday()


@pytest.fixture
def payload(workday):
    return {
        "requestKey": str(uuid.uuid4()),
        "name": "QA Test Visitor",
        "email": "qa@example.test",
        "organization": "Flowly QA Fixture",
        "kind": "discovery",
        "audience": "business",
        "requirements": "Test fixture: connect an inventory system with automated operational reporting.",
        "consent": True,
        "timezone": "Africa/Cairo",
        "language": "en",
        "date": workday,
        "time": "11:00",
    }


@pytest.fixture
def password():
    return PASSWORD


__all__ = ["override_settings"]
