import uuid

import pytest

from apps.accounts.serializers import ChangePasswordSerializer, RegisterSerializer
from apps.leads.serializers import (
    AssistantSerializer,
    RequestCreateSerializer,
    RequestLookupSerializer,
    RequestUpdateSerializer,
    valid_future_date,
)
from tests.conftest import future_workday
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def base(**over):
    data = {
        "requestKey": str(uuid.uuid4()),
        "name": "Ann Lee",
        "email": "ann@example.test",
        "organization": "Acme",
        "kind": "contact",
        "audience": "business",
        "requirements": "x" * 25,
        "consent": True,
        "timezone": "Africa/Cairo",
        "language": "en",
    }
    data.update(over)
    return data


def errors(**over):
    s = RequestCreateSerializer(data=base(**over))
    assert not s.is_valid()
    return s.errors


def test_valid_minimal_request():
    s = RequestCreateSerializer(data=base())
    assert s.is_valid(), s.errors
    assert s.validated_data["role"] == "" and s.validated_data["goals"] == []


@pytest.mark.parametrize(
    "field",
    [
        "requestKey",
        "name",
        "email",
        "organization",
        "kind",
        "audience",
        "requirements",
        "consent",
        "timezone",
        "language",
    ],
)
def test_required_fields(field):
    data = base()
    data.pop(field)
    s = RequestCreateSerializer(data=data)
    assert not s.is_valid() and field in s.errors


def test_consent_must_be_true():
    assert "consent" in errors(consent=False)


def test_bad_email_short_name_short_requirements():
    assert "email" in errors(email="bad")
    assert "name" in errors(name="A")
    assert "requirements" in errors(requirements="too short")


def test_wrong_types_and_choices():
    assert "kind" in errors(kind="newsletter")
    assert "timezone" in errors(timezone="UTC")
    assert "language" in errors(language="fr")
    assert "goals" in errors(goals=["x"] * 11)
    assert "recommended" in errors(recommended=["a"] * 5)
    assert "time" in errors(time="09:00", date="2030-01-01")


def test_government_requires_department():
    assert "department" in errors(audience="government", department="  ")


def test_date_and_time_must_come_together():
    assert "date" in errors(date="2030-01-02")
    assert "date" in errors(time="10:00")


def test_consultation_requires_date():
    assert "date" in errors(kind="consultation")


def test_lookup_normalises_and_validates_reference():
    s = RequestLookupSerializer(data={"reference": " flw-20261104-abcdef12 ", "email": " A@B.Test "})
    assert s.is_valid(), s.errors
    assert s.validated_data == {"reference": "FLW-20261104-ABCDEF12", "email": "a@b.test"}
    assert not RequestLookupSerializer(data={"reference": "nope", "email": "a@b.test"}).is_valid()


def test_update_serializer_rejects_unknown_status():
    assert not RequestUpdateSerializer(data={"status": "archived"}).is_valid()
    assert RequestUpdateSerializer(data={"status": "confirmed"}).is_valid()


def test_assistant_serializer_limits():
    assert AssistantSerializer(data={"message": "hi", "language": "en"}).is_valid()
    assert not AssistantSerializer(data={"message": "", "language": "en"}).is_valid()
    assert not AssistantSerializer(data={"message": "x" * 2001, "language": "en"}).is_valid()
    assert not AssistantSerializer(
        data={"message": "hi", "language": "en", "history": [{"role": "bot", "content": "x"}]}
    ).is_valid()


def test_valid_future_date_rules():
    assert valid_future_date(future_workday())
    assert not valid_future_date("2020-01-01")
    assert not valid_future_date("2026-02-30")
    assert not valid_future_date("not-a-date")
    assert not valid_future_date(future_workday(days=200))


def test_register_serializer_rules():
    ok = RegisterSerializer(
        data={"email": "New@Example.test", "password": "Str0ng-Pass!word", "password_confirm": "Str0ng-Pass!word"}
    )
    assert ok.is_valid(), ok.errors
    assert ok.validated_data["email"] == "new@example.test"
    assert not RegisterSerializer(data={"email": "x@example.test", "password": "short"}).is_valid()
    assert not RegisterSerializer(data={"email": "x@example.test", "password": "password"}).is_valid()
    mismatch = RegisterSerializer(
        data={"email": "x@example.test", "password": "Str0ng-Pass!word", "password_confirm": "other"}
    )
    assert not mismatch.is_valid() and "password_confirm" in mismatch.errors


def test_register_rejects_duplicate_email_case_insensitively():
    UserFactory(email="taken@example.test")
    s = RegisterSerializer(data={"email": "TAKEN@example.test", "password": "Str0ng-Pass!word"})
    assert not s.is_valid() and "email" in s.errors


def test_change_password_requires_correct_current(rf, user, password):
    request = rf.post("/")
    request.user = user
    bad = ChangePasswordSerializer(
        data={"current_password": "wrong", "new_password": "An0ther-Str0ng!pw"}, context={"request": request}
    )
    assert not bad.is_valid() and "current_password" in bad.errors
    same = ChangePasswordSerializer(
        data={"current_password": password, "new_password": password}, context={"request": request}
    )
    assert not same.is_valid()
    good = ChangePasswordSerializer(
        data={"current_password": password, "new_password": "An0ther-Str0ng!pw"}, context={"request": request}
    )
    assert good.is_valid(), good.errors
