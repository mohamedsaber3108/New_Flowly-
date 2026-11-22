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


def test_dashboard_reports_live_figures(admin_client):
    RequestFactory(status="pending_review", kind="consultation", audience="government", organization="Ministry X")
    RequestFactory(status="confirmed", kind="contact")
    AppointmentFactory(
        request=RequestFactory(organization="Booked Org"), date="2099-01-05", slot="2099-01-05T10:00", time="10:00"
    )
    response = admin_client.get("/admin/")
    ctx = response.context
    assert response.status_code == 200
    assert ctx["flowly_total_requests"] == 3 and ctx["flowly_pending"] == 2 and ctx["flowly_last_30"] == 3
    assert sum(p["count"] for p in ctx["flowly_weekly"]) == 3, "all of this week's requests are in the chart"
    assert {s["label"]: s["count"] for s in ctx["flowly_by_kind"]}["Consultation"] == 1
    assert ctx["flowly_upcoming"] == 1 and b"Booked Org" in response.content and b"Ministry X" in response.content
    assert b"status__exact=pending_review" in response.content


def _change_form_data(admin_client, req, **changes):
    """Current change-form values (including inline management forms) with the given edits applied."""
    from django.urls import reverse

    url = reverse("admin:leads_request_change", args=[req.pk])
    form = admin_client.get(url).context["adminform"].form
    data = {name: form[name].value() or "" for name in form.fields}
    data.update({k: "" if v is None else v for k, v in changes.items()})
    for prefix, count in (("appointments", req.appointments.count()), ("events", req.events.count())):
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": str(count),
                f"{prefix}-INITIAL_FORMS": str(count),
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
            }
        )
    for i, a in enumerate(req.appointments.order_by("pk")):
        data.update(
            {
                f"appointments-{i}-id": str(a.pk),
                f"appointments-{i}-request": str(req.pk),
                f"appointments-{i}-status": a.status,
            }
        )
    for i, e in enumerate(req.events.order_by("created_at", "pk")):
        data.update({f"events-{i}-id": str(e.pk), f"events-{i}-request": str(req.pk)})
    return url, data


def test_admin_status_edit_frees_slot_emails_customer_and_logs_actor(admin_client):
    from django.core import mail

    req = RequestFactory()
    AppointmentFactory(request=req)
    url, data = _change_form_data(admin_client, req, status="declined", internal_note="Out of scope")
    mail.outbox.clear()
    response = admin_client.post(url, data)
    assert response.status_code == 302, getattr(response, "context", {}) and response.context["adminform"].form.errors
    req.refresh_from_db()
    assert req.status == "declined" and req.internal_note == "Out of scope"
    assert Appointment.objects.get(request=req).status == "canceled"
    event = req.events.get(event_type="status_changed")
    assert event.status == "declined" and event.actor.email == "root@example.test"
    assert len(mail.outbox) == 1 and req.reference in mail.outbox[0].subject


def test_admin_status_edit_reports_slot_conflict_instead_of_crashing(admin_client):
    old = RequestFactory(status="canceled")
    AppointmentFactory(request=old, status="canceled")
    AppointmentFactory(request=RequestFactory())
    url, data = _change_form_data(admin_client, old, status="confirmed")
    response = admin_client.post(url, data, follow=True)
    assert response.status_code == 200
    assert Request.objects.get(pk=old.pk).status == "canceled"
    assert "slot is now held" in response.content.decode()


def test_admin_assignee_choices_are_active_team_members(admin_client):
    from django.urls import reverse

    from tests.factories import StaffFactory

    staff = StaffFactory(email="crew@example.test")
    UserFactory(email="customer@example.test")
    gone = StaffFactory(email="gone@example.test")
    gone.soft_delete()
    req = RequestFactory()
    form = admin_client.get(reverse("admin:leads_request_change", args=[req.pk])).context["adminform"].form
    emails = set(form.fields["assigned_to"].queryset.values_list("email", flat=True))
    assert "crew@example.test" in emails and "customer@example.test" not in emails and "gone@example.test" not in emails
    url, data = _change_form_data(admin_client, req, assigned_to=str(staff.pk))
    assert admin_client.post(url, data).status_code == 302
    req.refresh_from_db()
    assert req.assigned_to == staff and req.events.filter(event_type="assigned").exists()
