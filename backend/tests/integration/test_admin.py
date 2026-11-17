import pytest
from django.test import Client
from django.urls import reverse

from apps.leads.models import Appointment, Request
from tests.factories import AppointmentFactory, RequestEventFactory, RequestFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    from apps.accounts.models import User

    admin = User.objects.create_superuser(email="root@example.test", password="Str0ng-Passw0rd!x")
    client = Client()
    client.force_login(admin)
    return client


def test_admin_requires_staff(client, user):
    assert client.get("/admin/", follow=False).status_code == 302
    client.force_login(user)
    assert client.get("/admin/", follow=False).status_code == 302  # customers are not staff


def test_admin_index_and_changelists_render(admin_client):
    req = RequestFactory()
    RequestEventFactory(request=req)
    AppointmentFactory(request=req)
    index = admin_client.get("/admin/")
    assert index.status_code == 200 and b"Total requests" in index.content
    for name in ("leads_request", "leads_appointment", "leads_requestevent", "leads_assistantmessage", "accounts_user"):
        response = admin_client.get(reverse(f"admin:{name}_changelist"))
        assert response.status_code == 200, name
    assert admin_client.get(reverse("admin:leads_request_change", args=[req.pk])).status_code == 200
    assert admin_client.get(reverse("admin:accounts_user_add")).status_code == 200
    assert admin_client.get(reverse("admin:accounts_user_change", args=[UserFactory().pk])).status_code == 200


def test_admin_search_and_filter(admin_client):
    RequestFactory(name="Findable Person")
    response = admin_client.get(
        reverse("admin:leads_request_changelist"), {"q": "Findable", "status": "pending_review"}
    )
    assert response.status_code == 200 and b"Findable Person" in response.content


def test_export_csv_action_neutralises_formulas(admin_client):
    req = RequestFactory(name="=HYPERLINK(1)", internal_note="+cmd")
    response = admin_client.post(
        reverse("admin:leads_request_changelist"),
        {"action": "export_csv", "_selected_action": [str(req.pk)]},
    )
    text = response.content.decode("utf-8-sig")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert "'=HYPERLINK(1)" in text and "'+cmd" in text


def test_bulk_status_action_updates_requests_and_events(admin_client):
    req = RequestFactory()
    AppointmentFactory(request=req)
    admin_client.post(
        reverse("admin:leads_request_changelist"),
        {"action": "mark_confirmed", "_selected_action": [str(req.pk)]},
    )
    req.refresh_from_db()
    assert req.status == "confirmed"
    assert Appointment.objects.get(request=req).status == "confirmed"
    assert req.events.filter(event_type="status_changed", status="confirmed").exists()


def test_bulk_action_reports_slot_conflict(admin_client):
    old = RequestFactory(status="canceled")
    AppointmentFactory(request=old, status="canceled")
    AppointmentFactory(request=RequestFactory())
    admin_client.post(
        reverse("admin:leads_request_changelist"),
        {"action": "mark_confirmed", "_selected_action": [str(old.pk)]},
    )
    assert Request.objects.get(pk=old.pk).status == "canceled"


def test_admin_url_is_configurable(settings):
    from config import urls

    assert settings.ADMIN_URL.endswith("/")
    assert urls.urlpatterns[0].pattern._route == settings.ADMIN_URL
