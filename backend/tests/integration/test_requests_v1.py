"""Versioned /api/v1 request, dashboard and team endpoints (enveloped)."""

import uuid

import pytest
from rest_framework.test import APIClient

from apps.leads.models import Appointment, RequestEvent
from tests.factories import AppointmentFactory, RequestEventFactory, RequestFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db
V1 = "/api/v1"


def make_request(**kw):
    req = RequestFactory(**kw)
    RequestEventFactory(request=req)
    return req


# --- public ----------------------------------------------------------------


def test_submit_v1_envelope_and_idempotency(api, payload):
    r = api.post(f"{V1}/requests/", payload, format="json")
    body = r.json()
    assert r.status_code == 201 and body["success"] is True and body["data"]["reference"].startswith("FLW-")
    again = api.post(f"{V1}/requests/", payload, format="json")
    assert again.status_code == 200 and again.json()["data"]["reference"] == body["data"]["reference"]


def test_submit_v1_validation_error_envelope(api, payload):
    r = api.post(f"{V1}/requests/", {**payload, "email": "nope"}, format="json")
    body = r.json()
    assert r.status_code == 400 and body["success"] is False and "email" in body["errors"]


def test_submit_v1_slot_conflict_is_409(api, payload):
    api.post(f"{V1}/requests/", payload, format="json")
    r = api.post(f"{V1}/requests/", {**payload, "requestKey": str(uuid.uuid4())}, format="json")
    assert r.status_code == 409 and r.json()["success"] is False


def test_lookup_and_availability_v1(api, payload):
    ref = api.post(f"{V1}/requests/", payload, format="json").json()["data"]["reference"]
    ok = api.post(f"{V1}/requests/lookup/", {"reference": ref, "email": payload["email"]}, format="json")
    assert ok.status_code == 200 and ok.json()["data"]["status"] == "pending_review"
    miss = api.post(f"{V1}/requests/lookup/", {"reference": ref, "email": "other@example.test"}, format="json")
    assert miss.status_code == 404 and miss.json()["success"] is False
    av = api.get(f"{V1}/availability/", {"date": payload["date"]})
    assert av.json()["data"]["busy"] == ["11:00"]
    assert api.get(f"{V1}/availability/", {"date": "2001-01-01"}).status_code == 400


def test_assistant_v1(api):
    assert api.get(f"{V1}/assistant/").json()["data"] == {"mode": "guide"}
    r = api.post(f"{V1}/assistant/", {"message": "sales crm", "language": "en"}, format="json")
    assert r.status_code == 200 and r.json()["data"]["links"]
    assert api.post(f"{V1}/assistant/", {"message": "", "language": "en"}, format="json").status_code == 400


# --- customer dashboard -------------------------------------------------------


def test_my_requests_only_shows_own_and_verified_email_matches(auth_client, user):
    mine = make_request(user=user)
    by_email = make_request(email=user.email)  # anonymous but same verified email
    make_request()  # someone else's
    r = auth_client.get(f"{V1}/requests/mine/")
    refs = {x["reference"] for x in r.json()["data"]["results"]}
    assert refs == {mine.reference, by_email.reference}
    assert r.json()["data"]["count"] == 2


def test_my_requests_unverified_email_does_not_expose_anonymous_requests(api):
    stranger = UserFactory(email="victim@example.test", verified=False)
    make_request(email="victim@example.test")
    client = APIClient()
    client.force_authenticate(stranger)
    assert client.get(f"{V1}/requests/mine/").json()["data"]["count"] == 0


def test_my_requests_filter_order_search_pagination(auth_client, user):
    for i in range(3):
        make_request(user=user, status="confirmed" if i == 0 else "pending_review", organization=f"Org{i}x")
    assert auth_client.get(f"{V1}/requests/mine/", {"status": "confirmed"}).json()["data"]["count"] == 1
    assert auth_client.get(f"{V1}/requests/mine/", {"search": "Org2x"}).json()["data"]["count"] == 1
    page = auth_client.get(f"{V1}/requests/mine/", {"page_size": 2}).json()["data"]
    assert len(page["results"]) == 2 and page["next"] and page["total_pages"] == 2
    asc = auth_client.get(f"{V1}/requests/mine/", {"ordering": "created_at"}).json()["data"]["results"]
    assert asc[0]["created_at"] <= asc[-1]["created_at"]


def test_my_request_detail_has_timeline_and_hides_internal_fields(auth_client, user):
    req = make_request(user=user, internal_note="secret")
    r = auth_client.get(f"{V1}/requests/mine/{req.reference}/")
    data = r.json()["data"]
    assert r.status_code == 200 and data["events"][0]["event_type"] == "submitted"
    assert "internal_note" not in data and "secret" not in r.content.decode()
    other = make_request()
    assert auth_client.get(f"{V1}/requests/mine/{other.reference}/").status_code == 404


def test_dashboard_summary(auth_client, user):
    req = make_request(user=user)
    AppointmentFactory(request=req)
    make_request(user=user, status="completed")
    data = auth_client.get(f"{V1}/dashboard/").json()["data"]
    assert data["total_requests"] == 2 and data["open_requests"] == 1
    assert data["next_appointment"]["reference"] == req.reference and len(data["recent"]) == 2


def test_dashboard_requires_auth(api):
    assert api.get(f"{V1}/dashboard/").status_code == 401
    assert api.get(f"{V1}/requests/mine/").status_code == 401


# --- team --------------------------------------------------------------------


def test_team_list_filters_search_and_order(staff_client):
    a = make_request(name="Alpha", status="confirmed", kind="contact")
    make_request(name="Beta", organization="Zeta Corp")
    assert staff_client.get(f"{V1}/admin/requests/").json()["data"]["count"] == 2
    assert [
        x["reference"]
        for x in staff_client.get(f"{V1}/admin/requests/", {"status": "confirmed"}).json()["data"]["results"]
    ] == [a.reference]
    assert staff_client.get(f"{V1}/admin/requests/", {"search": "zeta"}).json()["data"]["count"] == 1
    assert staff_client.get(f"{V1}/admin/requests/", {"kind": "contact"}).json()["data"]["count"] == 1
    names = [
        x["name"] for x in staff_client.get(f"{V1}/admin/requests/", {"ordering": "name"}).json()["data"]["results"]
    ]
    assert names == ["Alpha", "Beta"]
    AppointmentFactory(request=a)
    assert staff_client.get(f"{V1}/admin/requests/", {"has_appointment": "true"}).json()["data"]["count"] == 1


def test_team_viewer_can_read_but_not_write(api):
    viewer = UserFactory(role="viewer")
    req = make_request()
    client = APIClient()
    client.force_authenticate(viewer)
    assert client.get(f"{V1}/admin/requests/").status_code == 200
    assert (
        client.patch(f"{V1}/admin/requests/{req.reference}/", {"status": "confirmed"}, format="json").status_code == 403
    )


def test_team_detail_patch_records_events_and_actor(staff_client, staff):
    req = make_request()
    r = staff_client.patch(
        f"{V1}/admin/requests/{req.reference}/",
        {"status": "in_review", "internal_note": "Call tomorrow", "assigned_to": staff.email},
        format="json",
    )
    data = r.json()["data"]
    assert r.status_code == 200 and data["status"] == "in_review" and data["assigned_to"] == staff.email
    types = [e["event_type"] for e in data["events"]]
    assert types == ["submitted", "status_changed", "note_updated", "assigned"]
    assert RequestEvent.objects.get(event_type="status_changed").actor == staff
    detail = staff_client.get(f"{V1}/admin/requests/{req.reference}/").json()["data"]
    assert detail["internal_note"] == "Call tomorrow"


def test_team_patch_validation_and_404(staff_client):
    req = make_request()
    assert staff_client.patch(f"{V1}/admin/requests/{req.reference}/", {}, format="json").status_code == 400
    assert (
        staff_client.patch(f"{V1}/admin/requests/{req.reference}/", {"status": "bogus"}, format="json").status_code
        == 400
    )
    assert (
        staff_client.patch(
            f"{V1}/admin/requests/{req.reference}/", {"assigned_to": "ghost@example.test"}, format="json"
        ).status_code
        == 400
    )
    assert staff_client.get(f"{V1}/admin/requests/FLW-20200101-FFFFFFFF/").status_code == 404


def test_team_patch_slot_conflict_is_409(staff_client):
    old = make_request(status="canceled")
    AppointmentFactory(request=old, status="canceled")
    AppointmentFactory(request=make_request())  # someone else now holds the slot
    r = staff_client.patch(f"{V1}/admin/requests/{old.reference}/", {"status": "confirmed"}, format="json")
    assert r.status_code == 409 and r.json()["success"] is False
    assert Appointment.objects.filter(request=old).first().status == "canceled"


def test_team_unassign(staff_client, staff):
    req = make_request(assigned_to=staff)
    r = staff_client.patch(f"{V1}/admin/requests/{req.reference}/", {"assigned_to": None}, format="json")
    assert r.status_code == 200 and r.json()["data"]["assigned_to"] is None


def test_team_stats(staff_client):
    make_request(status="confirmed")
    make_request()
    data = staff_client.get(f"{V1}/admin/stats/").json()["data"]
    assert data["total"] == 2 and data["by_status"]["confirmed"] == 1


def test_team_endpoints_accept_admin_token_only_when_allowed(api, settings):
    make_request()
    header = {"HTTP_AUTHORIZATION": f"Bearer {settings.ADMIN_TOKEN}"}
    assert settings.ALLOW_SHARED_ADMIN_TOKEN is False  # FL-08 default: the old key is refused
    assert api.get(f"{V1}/admin/requests/", **header).status_code == 401
    assert api.get("/api/admin/requests", **header).status_code == 401
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    assert api.get(f"{V1}/admin/requests/", **header).status_code == 200
    assert api.get("/api/admin/requests", **header).status_code == 200


def test_team_changes_by_named_staff_always_record_an_actor(api, staff, settings):
    """FL-08: with the shared key off, every event written through the team routes has a real user."""
    from rest_framework_simplejwt.tokens import RefreshToken

    assert settings.ALLOW_SHARED_ADMIN_TOKEN is False
    header = {"HTTP_AUTHORIZATION": f"Bearer {RefreshToken.for_user(staff).access_token}"}
    req = make_request()
    r1 = api.patch(f"{V1}/admin/requests/{req.reference}/", {"status": "confirmed"}, format="json", **header)
    r2 = api.patch(f"{V1}/admin/requests/{req.reference}/", {"internal_note": "called"}, format="json", **header)
    r3 = api.patch(
        f"/api/admin/requests/{req.reference}", {"status": "proposal_sent", "internalNote": ""}, format="json", **header
    )
    assert (r1.status_code, r2.status_code, r3.status_code) == (200, 200, 200)
    written = RequestEvent.objects.filter(request=req).exclude(event_type="submitted")
    assert written.count() >= 3
    assert all(event.actor_id == staff.id for event in written)


def test_health_reports_whether_the_shared_key_is_allowed(api, settings):
    assert api.get("/api/health").json()["sharedAdminToken"] is False
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    assert api.get("/api/health").json()["sharedAdminToken"] is True
    settings.ADMIN_TOKEN = ""  # allowed but no usable key: the field must stay hidden
    body = api.get("/api/health").json()
    assert body["sharedAdminToken"] is False
    assert "ADMIN_TOKEN" not in str(body)


def test_team_endpoints_reject_anonymous(api):
    assert api.get(f"{V1}/admin/requests/").status_code == 401
    assert api.get(f"{V1}/admin/stats/").status_code == 401


# --- errors / docs ---------------------------------------------------------------


def test_unknown_v1_route_envelope_not_required_but_404(api):
    assert api.get(f"{V1}/nothing/").status_code == 404


def test_unhandled_exception_returns_clean_500_envelope(api):
    from unittest import mock

    with mock.patch("apps.leads.views.intake.availability", side_effect=RuntimeError("boom")):
        client = APIClient(raise_request_exception=False)
        r = client.get(f"{V1}/availability/", {"date": "2030-01-01"})
    body = r.json()
    assert r.status_code == 500 and body["success"] is False and "boom" not in str(body)


def test_database_error_returns_503_envelope(api):
    from unittest import mock

    from django.db import DatabaseError

    with mock.patch("apps.leads.views.intake.availability", side_effect=DatabaseError("down")):
        r = api.get(f"{V1}/availability/", {"date": "2030-01-01"})
    assert r.status_code == 503 and r.json()["success"] is False


def test_openapi_schema_and_swagger_ui(api):
    schema = api.get("/api/schema/", HTTP_ACCEPT="application/json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    for expected in (
        "/api/v1/auth/login/",
        "/api/v1/users/me/",
        "/api/v1/requests/",
        "/api/v1/admin/requests/",
        "/api/requests",
    ):
        assert expected in paths, expected
    assert api.get("/api/docs/").status_code == 200
    assert api.get("/api/redoc/").status_code == 200


def test_account_portal_page_renders(api):
    r = api.get("/account/")
    assert r.status_code == 200 and b"portal.js" in r.content


def test_admin_login_page_uses_configured_path(api):
    assert api.get("/admin/login/").status_code == 200


def test_staff_factory_sanity():
    assert StaffFactory().role == "staff"


def test_team_console_history_works_with_admin_token_and_staff_jwt(api, staff, settings):
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    req = make_request()
    url = f"{V1}/admin/requests/{req.reference}/"
    by_token = api.get(url, HTTP_AUTHORIZATION=f"Bearer {settings.ADMIN_TOKEN}")
    assert by_token.status_code == 200 and by_token.json()["data"]["events"][0]["event_type"] == "submitted"
    from rest_framework_simplejwt.tokens import RefreshToken

    by_jwt = api.get(url, HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(staff).access_token}")
    assert by_jwt.status_code == 200


def test_account_portal_shows_google_only_when_configured(api, settings):
    assert b'data-google="1"' in api.get("/account/").content
    settings.GOOGLE_CLIENT_ID = ""
    assert b'data-google="0"' in api.get("/account/").content
