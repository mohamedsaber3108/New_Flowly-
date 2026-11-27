"""The original frontend contract (/api/*). Mirrors tests/api-integration.mjs from the React project."""

import json
import uuid
from unittest import mock

import pytest
from django.core import mail

from apps.leads.models import Request, RequestEvent
from tests.factories import StaffFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def shared_key_allowed(settings):
    """These tests cover the original /team contract, which signs in with the shared ADMIN_TOKEN.

    FL-08 turns that off by default (ALLOW_SHARED_ADMIN_TOKEN=False); the off state is tested in test_requests_v1.py
    and test_permission_matrix.py.
    """
    settings.ALLOW_SHARED_ADMIN_TOKEN = True


ORIGIN = "http://testserver"
TOKEN = "flowly-local-test-admin-token-123456789"


def post(client, path, data, origin=ORIGIN, **extra):
    headers = {"HTTP_ORIGIN": origin} if origin else {}
    return client.post(path, data=json.dumps(data), content_type="application/json", **headers, **extra)


def admin_headers():
    return {"HTTP_AUTHORIZATION": f"Bearer {TOKEN}", "HTTP_ORIGIN": ORIGIN}


# --- intake ---------------------------------------------------------------


def test_server_enforces_consent(api, payload):
    r = post(api, "/api/requests", {**payload, "consent": False})
    assert r.status_code == 400 and "error" in r.json()


def test_server_validates_email(api, payload):
    assert post(api, "/api/requests", {**payload, "email": "bad"}).status_code == 400


def test_past_dates_rejected(api, payload):
    assert post(api, "/api/requests", {**payload, "date": "2020-01-01"}).status_code == 400


def test_weekend_and_far_dates_rejected(api, payload):
    assert post(api, "/api/requests", {**payload, "date": "2099-01-01"}).status_code == 400


def test_government_department_required(api, payload):
    r = post(api, "/api/requests", {**payload, "audience": "government", "department": ""})
    assert r.status_code == 400


def test_cross_origin_submission_rejected(api, payload):
    assert post(api, "/api/requests", payload, origin="https://unrelated.example").status_code == 403


def test_invalid_json_and_oversized_body(api):
    assert api.post("/api/requests", data="{nope", content_type="application/json").status_code == 400
    assert (
        api.post("/api/requests", data=json.dumps({"x": "a" * 26000}), content_type="application/json").status_code
        == 413
    )


def test_request_saved_with_reference_and_provisional_appointment(api, payload):
    r = post(api, "/api/requests", payload)
    body = r.json()
    assert r.status_code == 201
    assert body["reference"].startswith("FLW-") and body["status"] == "pending_review"
    assert body["appointment"] == {
        "date": payload["date"],
        "time": "11:00",
        "timezone": "Africa/Cairo",
        "status": "provisional",
    }
    req = Request.objects.get(reference=body["reference"])
    assert str(req.id) == payload["requestKey"]
    assert list(req.events.values_list("event_type", flat=True)) == ["submitted"]
    assert r["Cache-Control"] == "no-store"


def test_safe_retry_is_idempotent(api, payload):
    first = post(api, "/api/requests", payload).json()
    r = post(api, "/api/requests", payload)
    assert r.status_code == 200 and r.json()["reference"] == first["reference"]
    assert Request.objects.count() == 1


def test_duplicate_consultation_slot_rejected(api, payload):
    assert post(api, "/api/requests", payload).status_code == 201
    r = post(api, "/api/requests", {**payload, "requestKey": str(uuid.uuid4())})
    assert r.status_code == 409
    assert Request.objects.count() == 1  # nothing partially saved


def test_request_without_appointment(api, payload):
    r = post(api, "/api/requests", {**payload, "date": None, "time": None})
    assert r.status_code == 201 and r.json()["appointment"] is None


def test_confirmation_email_sent_to_visitor(api, payload, settings):
    settings.TEAM_NOTIFY_EMAIL = "team@example.test"
    post(api, "/api/requests", payload)
    recipients = [m.to[0] for m in mail.outbox]
    assert payload["email"] in recipients and "team@example.test" in recipients


def test_rate_limit_after_eight_requests(api, payload):
    for _ in range(8):
        assert (
            post(
                api, "/api/requests", {**payload, "requestKey": str(uuid.uuid4()), "date": None, "time": None}
            ).status_code
            == 201
        )
    r = post(api, "/api/requests", {**payload, "requestKey": str(uuid.uuid4()), "date": None, "time": None})
    assert r.status_code == 429 and "error" in r.json()


def test_authenticated_submission_links_the_user(api, payload, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    token = str(RefreshToken.for_user(user).access_token)
    r = post(api, "/api/requests", payload, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r.status_code == 201
    assert Request.objects.get(reference=r.json()["reference"]).user == user


def test_bad_token_on_public_endpoint_is_ignored(api, payload):
    r = post(api, "/api/requests", payload, HTTP_AUTHORIZATION="Bearer not-a-jwt")
    assert r.status_code == 201


# --- availability ----------------------------------------------------------


def test_saved_slot_appears_in_availability(api, payload):
    post(api, "/api/requests", payload)
    data = api.get("/api/availability", {"date": payload["date"]}).json()
    assert data["busy"] == ["11:00"] and data["timezone"] == "Africa/Cairo"


def test_availability_validates_date(api):
    assert api.get("/api/availability", {"date": "garbage"}).status_code == 400
    assert api.get("/api/availability").status_code == 400


# --- tracking --------------------------------------------------------------


def test_status_requires_matching_email(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    r = post(api, "/api/request-status", {"reference": ref, "email": "not-the-customer@example.test"})
    assert r.status_code == 404


def test_customer_can_track_pending_request(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    r = post(api, "/api/request-status", {"reference": ref.lower(), "email": payload["email"].upper()})
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "pending_review" and body["appointment"]["time"] == "11:00"
    assert set(body) == {"reference", "kind", "status", "createdAt", "updatedAt", "appointment"}
    assert body["updatedAt"] is None
    assert body["createdAt"].endswith("Z")


def test_status_rejects_bad_input(api):
    assert post(api, "/api/request-status", {"reference": "x", "email": "bad"}).status_code == 400
    assert post(api, "/api/request-status", {"reference": "x", "email": "a@b.test"}).status_code == 400


# --- team console ----------------------------------------------------------


def test_admin_list_rejects_anonymous_and_wrong_token(api):
    assert api.get("/api/admin/requests").status_code == 401
    assert api.get("/api/admin/requests", HTTP_AUTHORIZATION="Bearer " + "x" * 40).status_code == 401


def test_owner_sees_saved_request_with_console_row_shape(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    r = api.get("/api/admin/requests", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
    assert r.status_code == 200
    row = next(x for x in r.json()["requests"] if x["reference"] == ref)
    assert set(row) == {
        "reference",
        "kind",
        "audience",
        "name",
        "email",
        "organization",
        "details",
        "status",
        "created_at",
        "updated_at",
        "internal_note",
        "date",
        "time",
        "timezone",
        "appointment_status",
    }
    assert json.loads(row["details"])["requirements"].startswith("Test fixture")
    assert row["date"] == payload["date"] and row["appointment_status"] == "provisional"


def test_full_status_lifecycle(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    url = f"/api/admin/requests/{ref}"
    r = api.patch(
        url,
        data=json.dumps({"status": "confirmed", "internalNote": "Call and send invitation manually."}),
        content_type="application/json",
        **admin_headers(),
    )
    assert r.status_code == 200 and r.json() == {"reference": ref, "status": "confirmed"}

    seen = post(api, "/api/request-status", {"reference": ref, "email": payload["email"]}).json()
    assert seen["status"] == "confirmed" and seen["appointment"]["status"] == "confirmed"
    assert seen["updatedAt"] is not None
    assert "Call and send" not in json.dumps(seen)  # private note never leaks

    r = api.patch(
        url,
        data=json.dumps({"status": "canceled", "internalNote": "Customer requested cancellation."}),
        content_type="application/json",
        **admin_headers(),
    )
    assert r.status_code == 200
    # canceled slot can be requested again
    assert post(api, "/api/requests", {**payload, "requestKey": str(uuid.uuid4())}).status_code == 201
    # the old appointment can no longer reclaim the slot
    r = api.patch(
        url,
        data=json.dumps({"status": "confirmed", "internalNote": ""}),
        content_type="application/json",
        **admin_headers(),
    )
    assert r.status_code == 409
    assert Request.objects.get(reference=ref).status == "canceled"  # rolled back


def test_status_events_recorded(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    api.patch(
        f"/api/admin/requests/{ref}",
        data=json.dumps({"status": "in_review", "internalNote": ""}),
        content_type="application/json",
        **admin_headers(),
    )
    events = list(RequestEvent.objects.filter(request__reference=ref).values_list("event_type", "status"))
    assert events == [("submitted", "pending_review"), ("status_changed", "in_review")]


def test_status_change_emails_the_customer(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    mail.outbox.clear()
    api.patch(
        f"/api/admin/requests/{ref}",
        data=json.dumps({"status": "proposal_sent", "internalNote": ""}),
        content_type="application/json",
        **admin_headers(),
    )
    assert len(mail.outbox) == 1 and ref in mail.outbox[0].subject


def test_admin_patch_guards(api, payload):
    ref = post(api, "/api/requests", payload).json()["reference"]
    body = json.dumps({"status": "confirmed", "internalNote": ""})
    assert api.patch(f"/api/admin/requests/{ref}", data=body, content_type="application/json").status_code == 401
    bad_origin = {"HTTP_AUTHORIZATION": f"Bearer {TOKEN}", "HTTP_ORIGIN": "https://evil.example"}
    assert (
        api.patch(f"/api/admin/requests/{ref}", data=body, content_type="application/json", **bad_origin).status_code
        == 403
    )
    assert (
        api.patch(
            "/api/admin/requests/not-a-ref", data=body, content_type="application/json", **admin_headers()
        ).status_code
        == 400
    )
    assert (
        api.patch(
            "/api/admin/requests/FLW-20200101-ABCDEF12", data=body, content_type="application/json", **admin_headers()
        ).status_code
        == 404
    )
    bad = json.dumps({"status": "archived"})
    assert (
        api.patch(
            f"/api/admin/requests/{ref}", data=bad, content_type="application/json", **admin_headers()
        ).status_code
        == 400
    )


def test_staff_jwt_can_use_the_team_console_but_customer_cannot(api, payload):
    from rest_framework_simplejwt.tokens import RefreshToken

    post(api, "/api/requests", payload)
    staff = StaffFactory()
    ok = api.get("/api/admin/requests", HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(staff).access_token}")
    assert ok.status_code == 200
    customer = UserFactory()
    denied = api.get("/api/admin/requests", HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(customer).access_token}")
    assert denied.status_code == 403


def test_admin_token_disabled_when_too_short(api, settings):
    settings.ADMIN_TOKEN = "short"
    assert api.get("/api/admin/requests", HTTP_AUTHORIZATION="Bearer short").status_code == 401


# --- assistant --------------------------------------------------------------


def test_assistant_guide_returns_relevant_service_links(api):
    assert api.get("/api/assistant").json() == {"mode": "guide"}
    r = post(api, "/api/assistant", {"message": "I need an AI ERP", "language": "en", "history": []})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "guide"
    assert any(link["url"] == "/services/ai-erp" for link in body["links"])


def test_assistant_arabic_government_routing(api):
    r = post(api, "/api/assistant", {"message": "عايز حلول لجهة حكومية", "language": "ar", "history": []})
    assert any("audience=government" in link["url"] for link in r.json()["links"])


def test_assistant_every_rule_resolves_real_services(api):
    for message in [
        "erp",
        "government",
        "private ai",
        "white label agency",
        "video content",
        "sales crm",
        "price",
        "hello",
    ]:
        body = post(api, "/api/assistant", {"message": message, "language": "en"}).json()
        assert len(body["links"]) >= 3 and body["reply"]


def test_assistant_validation_and_origin(api):
    assert post(api, "/api/assistant", {"message": "", "language": "en"}).status_code == 400
    assert (
        post(api, "/api/assistant", {"message": "hi", "language": "en"}, origin="https://evil.example").status_code
        == 403
    )


def test_assistant_uses_compatible_provider_when_configured(api, settings):
    settings.AI_API_URL, settings.AI_API_KEY, settings.AI_MODEL = "https://ai.example/v1/chat", "k", "m"
    settings.ASSISTANT_AI_ENABLED = True  # FL-17: the kill switch is off by default
    fake = mock.Mock(status_code=200)
    fake.json.return_value = {"choices": [{"message": {"content": "Live AI answer"}}]}
    fake.raise_for_status.return_value = None
    with mock.patch("apps.leads.assistant.requests.post", return_value=fake) as call:
        assert api.get("/api/assistant").json() == {"mode": "ai"}
        body = post(
            api,
            "/api/assistant",
            {"message": "hello", "language": "en", "history": [{"role": "user", "content": "hello"}]},
        ).json()
    assert body["mode"] == "ai" and body["source"] == "ai"
    assert body["reply"] == "Live AI answer" and len(body["links"]) == 3
    sent = call.call_args.kwargs["json"]
    assert sent["model"] == "m" and sent["messages"][0]["role"] == "system"
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]  # duplicated last turn removed


def test_assistant_falls_back_when_provider_fails(api, settings):
    settings.AI_API_URL, settings.AI_API_KEY, settings.AI_MODEL = "https://ai.example/v1/chat", "k", "m"
    settings.ASSISTANT_AI_ENABLED = True
    with mock.patch("apps.leads.assistant.requests.post", side_effect=RuntimeError("down")):
        body = post(api, "/api/assistant", {"message": "erp please", "language": "en"}).json()
    assert body["mode"] == "guide" and body["reply"].startswith("The AI connection is unavailable")


def test_assistant_logging_is_opt_in(api, settings):
    from apps.leads.models import AssistantMessage

    post(api, "/api/assistant", {"message": "hello", "language": "en"})
    assert AssistantMessage.objects.count() == 0
    settings.ASSISTANT_LOG_ENABLED = True
    post(api, "/api/assistant", {"message": "hello", "language": "en"})
    assert AssistantMessage.objects.count() == 1


# --- system ---------------------------------------------------------------


def test_health_endpoints(api, settings):
    settings.ALLOW_SHARED_ADMIN_TOKEN = False
    r = api.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "flowly-web", "storage": "ok", "sharedAdminToken": False}
    r2 = api.get("/health/")
    assert r2.status_code == 200 and r2.json()["success"] is True and r2.json()["data"]["database"] == "ok"


def test_sitemap_and_robots(api):
    sitemap = api.get("/sitemap.xml").content.decode()
    assert "/services/ai-erp" in sitemap and "/government" in sitemap
    assert sitemap.count("<url>") == 8 + 45 + 14 + 3
    robots = api.get("/robots.txt").content.decode()
    assert "Disallow: /team" in robots and "Disallow: /api/" in robots and "Sitemap:" in robots


def test_public_origin_setting_is_used_in_sitemap(api, settings):
    settings.PUBLIC_ORIGIN = "https://flowly.example"
    assert "https://flowly.example/services" in api.get("/sitemap.xml").content.decode()


def test_unknown_api_path_is_404(api):
    assert api.get("/api/nope").status_code == 404
