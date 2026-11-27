"""Audit log (FL-10): every recorded action, fail-closed behaviour, insert-only, no secrets."""

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.contrib import admin as django_admin
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import Client
from django.test import RequestFactory as DjangoRequestFactory
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.admin import UserAdmin
from apps.accounts.models import User
from apps.audit import service as audit
from apps.audit.models import AuditEntry, AuditError
from tests.factories import PASSWORD, RequestFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fresh_cache():
    """The once-a-minute denied-row limit lives in the cache; ids repeat between tests, so start clean."""
    cache.clear()


V1 = "/api/v1"
A = AuditEntry.Action
R = AuditEntry.Result


def only(action, **filters):
    return AuditEntry.objects.get(action=action, **filters)


def bearer(user):
    return {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(user)}"}


def write_fails():
    """Make every audit insert fail, as if the table were unavailable."""
    return mock.patch.object(AuditEntry.objects, "create", side_effect=DatabaseError("audit down"))


# --- insert-only ------------------------------------------------------------------------------------------------------


def test_stored_entry_cannot_be_changed_or_deleted():
    entry = audit.record(A.SETTINGS, target_type="setting", target_id="x")
    entry.reason = "tampered"
    with pytest.raises(AuditError):
        entry.save()
    with pytest.raises(AuditError):
        entry.delete()
    with pytest.raises(AuditError):
        AuditEntry.objects.all().update(reason="tampered")
    with pytest.raises(AuditError):
        AuditEntry.objects.all().delete()
    assert AuditEntry.objects.get(pk=entry.pk).reason == ""


# --- no secrets -------------------------------------------------------------------------------------------------------


def test_secret_looking_fields_are_never_stored():
    entry = audit.record(
        A.SETTINGS,
        before={"password": "hunter2", "nested": {"api_key": "k-123", "name": "ok"}, "list": [{"token": "t"}]},
        after={"ADMIN_TOKEN": "abc", "note": "x" * 900},
    )
    stored = json.dumps([entry.before, entry.after])
    for secret in ("hunter2", "k-123", '"t"', "abc"):
        assert secret not in stored
    assert entry.before["nested"]["name"] == "ok"
    assert entry.before["password"] == "[redacted]"
    assert len(entry.after["note"]) <= 501


# --- sign-in ----------------------------------------------------------------------------------------------------------


def test_api_login_failure_and_success_are_recorded_without_the_password():
    user = UserFactory()
    api = APIClient()
    bad = api.post(f"{V1}/auth/login/", {"email": user.email, "password": "Wrong-Password-1!"}, format="json")
    assert bad.status_code == 401
    failed = only(A.LOGIN_FAILED)
    assert failed.result == R.FAILED and failed.after["email"] == user.email

    ok = api.post(f"{V1}/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert ok.status_code == 200
    login = only(A.LOGIN, actor_id=user.pk)
    assert login.result == R.SUCCESS and login.actor_role == "customer" and login.after == {"via": "api"}

    everything = json.dumps(list(AuditEntry.objects.values()), default=str)
    assert "Wrong-Password-1!" not in everything and PASSWORD not in everything


def test_django_admin_login_failure_and_success_are_recorded():
    staff = StaffFactory()
    client = Client()
    assert client.login(username=staff.email, password="nope-nope-nope") is False
    assert only(A.LOGIN_FAILED).after["email"] == staff.email
    assert client.login(username=staff.email, password=PASSWORD) is True
    assert only(A.LOGIN, actor_id=staff.pk).after == {"via": "django-session"}


def test_disabled_account_login_is_recorded_as_denied():
    suspended = UserFactory(status="suspended")
    r = APIClient().post(f"{V1}/auth/login/", {"email": suspended.email, "password": PASSWORD}, format="json")
    assert r.status_code == 403
    entry = only(A.LOGIN_FAILED, result=R.DENIED)
    assert entry.after["why"] == "account disabled"


# --- requests: status, assignee, note ---------------------------------------------------------------------------------


def test_request_status_assignee_and_note_changes_are_recorded_with_the_actor():
    staff, assignee = StaffFactory(), StaffFactory()
    req = RequestFactory()
    r = APIClient().patch(
        f"{V1}/admin/requests/{req.reference}/",
        {"status": "in_review", "internal_note": "Call tomorrow", "assigned_to": assignee.email},
        format="json",
        **bearer(staff),
    )
    assert r.status_code == 200
    status = only(A.REQUEST_STATUS)
    assert (status.actor_id, status.actor_role, status.target_id) == (staff.pk, "staff", req.reference)
    assert status.before == {"status": "pending_review"} and status.after == {"status": "in_review"}
    assert only(A.REQUEST_NOTE).after == {"internal_note": "Call tomorrow"}
    assign = only(A.REQUEST_ASSIGN)
    assert assign.actor_id == staff.pk and assign.after == {"assigned_to": assignee.email}
    assert req.events.count() == 3  # the request event timeline is still written next to the audit log


def test_a_failed_audit_write_does_not_block_a_request_update():
    staff = StaffFactory()
    req = RequestFactory()
    with write_fails():
        r = APIClient().patch(
            f"{V1}/admin/requests/{req.reference}/", {"status": "confirmed"}, format="json", **bearer(staff)
        )
    assert r.status_code == 200
    req.refresh_from_db()
    assert req.status == "confirmed" and req.events.filter(event_type="status_changed").exists()


# --- users: role, suspend, delete -------------------------------------------------------------------------------------


def make_admin_request(actor):
    request = DjangoRequestFactory().post("/admin/accounts/user/1/change/", HTTP_USER_AGENT="pytest")
    request.user = actor
    return request


def save_through_admin(actor, user):
    model_admin = UserAdmin(User, django_admin.site)
    with transaction.atomic():  # Django wraps the admin save in a transaction too
        model_admin.save_model(make_admin_request(actor), user, form=None, change=True)


def test_role_change_is_recorded_with_before_and_after():
    owner = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
    target = UserFactory()
    target.role = "staff"
    target.is_staff = True
    save_through_admin(owner, target)
    entry = only(A.USER_ROLE, target_id=str(target.pk))
    assert entry.actor_id == owner.pk and entry.result == R.SUCCESS
    assert entry.before == {"role": "customer", "is_staff": False}
    assert entry.after == {"role": "staff", "is_staff": True}


def test_suspend_and_reactivate_are_recorded():
    owner = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
    target = UserFactory()
    target.status = "suspended"
    save_through_admin(owner, target)
    assert only(A.USER_SUSPEND).after == {"status": "suspended"}
    target.status = "active"
    save_through_admin(owner, target)
    assert only(A.USER_REACTIVATE).after == {"status": "active"}


def test_role_change_fails_closed_when_the_audit_write_fails():
    owner = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
    target = UserFactory()
    target.role = "owner"
    with write_fails(), pytest.raises(DatabaseError):
        save_through_admin(owner, target)
    assert User.objects.get(pk=target.pk).role == "customer"


def test_soft_delete_is_recorded_and_fails_closed():
    staff, victim, other = StaffFactory(), UserFactory(), UserFactory()
    victim.soft_delete(actor=staff, reason="Spam account")
    entry = only(A.USER_DELETE, target_id=str(victim.pk))
    assert (entry.actor_id, entry.reason) == (staff.pk, "Spam account")
    assert entry.after == {"is_deleted": True, "is_active": False}

    with write_fails(), pytest.raises(DatabaseError):
        other.soft_delete(actor=staff)
    other.refresh_from_db()
    assert other.is_deleted is False and other.is_active is True


def test_self_service_delete_records_the_user_as_actor():
    user = UserFactory()
    r = APIClient().delete(f"{V1}/users/me/", {"password": PASSWORD}, format="json", **bearer(user))
    assert r.status_code == 200
    entry = only(A.USER_DELETE)
    assert entry.actor_id == user.pk and entry.reason == "Self-service account deletion"


# --- export -----------------------------------------------------------------------------------------------------------


@pytest.fixture
def admin_client():
    root = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
    client = Client()
    client.force_login(root)
    return client, root


def test_csv_export_is_recorded_and_fails_closed(admin_client):
    client, root = admin_client
    req = RequestFactory()
    url = "/admin/leads/request/"
    ok = client.post(url, {"action": "export_csv", "_selected_action": [str(req.pk)]})
    assert ok.status_code == 200 and ok["Content-Type"].startswith("text/csv")
    entry = only(A.EXPORT_REQUESTS)
    assert entry.actor_id == root.pk and entry.after["count"] == 1

    with write_fails(), pytest.raises(DatabaseError):
        client.post(url, {"action": "export_csv", "_selected_action": [str(req.pk)]})


def test_export_audit_log_command_writes_jsonl_and_matching_sha256(tmp_path):
    audit.record(A.SETTINGS, target_type="setting", target_id="one", after={"v": 1})
    today = datetime.now(timezone.utc).date().isoformat()
    call_command("export_audit_log", "--date", today, "--out-dir", str(tmp_path))
    data = (tmp_path / f"audit-{today}.jsonl").read_bytes()
    lines = [json.loads(line) for line in data.decode().splitlines()]
    assert any(line["target_id"] == "one" and line["after"] == {"v": 1} for line in lines)
    sha_line = (tmp_path / f"audit-{today}.jsonl.sha256").read_text().split()
    assert sha_line == [hashlib.sha256(data).hexdigest(), f"audit-{today}.jsonl"]
    assert only(A.EXPORT_AUDIT, target_id=today).reason.startswith("Daily export")
    # The files hold emails and IP addresses: owner-only files in an owner-only folder.
    assert stat.S_IMODE(os.stat(tmp_path).st_mode) == 0o700
    for name in (f"audit-{today}.jsonl", f"audit-{today}.jsonl.sha256"):
        assert stat.S_IMODE(os.stat(tmp_path / name).st_mode) == 0o600


def test_export_audit_log_command_fails_closed(tmp_path):
    today = datetime.now(timezone.utc).date().isoformat()
    with write_fails(), pytest.raises(DatabaseError):
        call_command("export_audit_log", "--date", today, "--out-dir", str(tmp_path))
    assert not list(tmp_path.iterdir())


# --- denied attempts --------------------------------------------------------------------------------------------------


def test_denied_calls_on_team_routes_are_recorded():
    customer = UserFactory()
    api = APIClient()
    assert api.get(f"{V1}/admin/requests/", **bearer(customer)).status_code == 403
    assert api.get("/api/admin/requests", **bearer(customer)).status_code == 403
    entries = AuditEntry.objects.filter(action=A.DENIED)
    assert entries.count() == 2
    first = entries.filter(target_id="/api/v1/admin/requests/").get()
    assert (first.actor_id, first.actor_role, first.result) == (customer.pk, "customer", R.DENIED)
    assert first.after["status"] == 403 and first.after["method"] == "GET"


def test_anonymous_probes_without_credentials_are_not_logged():
    assert APIClient().get(f"{V1}/admin/requests/").status_code == 401
    assert not AuditEntry.objects.filter(action=A.DENIED).exists()


@pytest.mark.parametrize("header", ["Basic x", "Bearer not-a-real-token", "Token abc", "Bearer "])
def test_unauthenticated_calls_with_any_authorization_header_write_no_rows(header):
    """The flood case: anyone on the internet can send these. 50 calls on each team API write 0 rows."""
    api = APIClient()
    for _ in range(50):
        assert api.get(f"{V1}/admin/requests/", HTTP_AUTHORIZATION=header).status_code == 401
        assert api.get("/api/admin/requests", HTTP_AUTHORIZATION=header).status_code == 401
    assert AuditEntry.objects.count() == 0


def test_a_signed_in_user_denied_ten_times_in_a_minute_writes_one_row_per_route():
    customer = UserFactory()
    api = APIClient()
    for _ in range(10):
        assert api.get(f"{V1}/admin/requests/", **bearer(customer)).status_code == 403
    assert AuditEntry.objects.filter(action=A.DENIED).count() == 1
    for _ in range(10):
        assert api.get("/api/admin/requests", **bearer(customer)).status_code == 403
    assert AuditEntry.objects.filter(action=A.DENIED).count() == 2  # a different route has its own window
    other = UserFactory()
    assert api.get(f"{V1}/admin/requests/", **bearer(other)).status_code == 403
    assert AuditEntry.objects.filter(action=A.DENIED).count() == 3  # and so does a different actor


def test_denied_rows_come_back_after_the_one_minute_window():
    customer = UserFactory()
    api = APIClient()
    api.get(f"{V1}/admin/requests/", **bearer(customer))
    cache.clear()  # what the cache does when the 60 seconds are over
    api.get(f"{V1}/admin/requests/", **bearer(customer))
    assert AuditEntry.objects.filter(action=A.DENIED).count() == 2


def test_a_mistyped_password_in_the_login_field_is_not_stored():
    typed = "Str0ng-Passw0rd!x"
    assert Client().login(username=typed, password="whatever") is False
    entry = only(A.LOGIN_FAILED)
    assert entry.after == {"email": "[not an email]"}
    assert typed not in json.dumps(list(AuditEntry.objects.values()), default=str)
    assert audit.safe_email("a@b.co") == "a@b.co" and audit.safe_email("a b@c.d") == "[not an email]"


# --- hard delete of users ---------------------------------------------------------------------------------------------


def test_admin_cannot_hard_delete_users_so_no_delete_goes_unaudited(admin_client):
    client, root = admin_client
    victim = UserFactory()
    model_admin = UserAdmin(User, django_admin.site)
    assert model_admin.has_delete_permission(make_admin_request(root)) is False
    assert client.get(f"/admin/accounts/user/{victim.pk}/delete/").status_code == 403
    assert client.post(f"/admin/accounts/user/{victim.pk}/delete/", {"post": "yes"}).status_code == 403
    client.post(
        "/admin/accounts/user/",
        {"action": "delete_selected", "_selected_action": [str(victim.pk)], "post": "yes"},
    )
    assert User.objects.filter(pk=victim.pk).exists()
    assert "delete_selected" not in model_admin.get_actions(make_admin_request(root))


def test_ticking_is_deleted_in_the_admin_form_is_audited_as_a_delete():
    owner = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
    target = UserFactory()
    target.is_deleted = True
    target.is_active = False
    save_through_admin(owner, target)
    entry = only(A.USER_DELETE, target_id=str(target.pk))
    assert entry.actor_id == owner.pk and entry.after == {"is_deleted": True, "is_active": False}


def test_purge_e2e_hard_delete_is_audited_and_fails_closed():
    gone = UserFactory(email="e2e-one@example.test")
    kept = UserFactory(email="e2e-two@example.test")
    with write_fails(), pytest.raises(DatabaseError):
        call_command("purge_e2e", "--yes")
    assert User.objects.filter(pk__in=[gone.pk, kept.pk]).count() == 2
    call_command("purge_e2e", "--yes")
    assert not User.objects.filter(pk__in=[gone.pk, kept.pk]).exists()
    assert AuditEntry.objects.filter(action=A.USER_DELETE, reason__startswith="purge_e2e").count() == 2


def test_a_failed_audit_write_never_changes_a_403():
    customer = UserFactory()
    with write_fails():
        assert APIClient().get(f"{V1}/admin/requests/", **bearer(customer)).status_code == 403


# --- request context --------------------------------------------------------------------------------------------------


def test_entries_carry_ip_client_and_request_id():
    user = UserFactory()
    r = APIClient().post(
        f"{V1}/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
        HTTP_USER_AGENT="pytest-agent/1.0",
        HTTP_X_REQUEST_ID="req-abc-123",
        REMOTE_ADDR="203.0.113.7",
    )
    assert r["X-Request-ID"] == "req-abc-123"
    entry = only(A.LOGIN)
    assert (entry.ip, entry.user_agent, entry.request_id) == ("203.0.113.7", "pytest-agent/1.0", "req-abc-123")


# --- settings hook ----------------------------------------------------------------------------------------------------


def test_settings_hook_records_a_sensitive_entry():
    owner = StaffFactory(role="owner")
    audit.record_settings_change("site.name", {"v": "A"}, {"v": "B"}, actor=owner, reason="Rename")
    entry = only(A.SETTINGS, target_id="site.name")
    assert entry.actor_id == owner.pk and entry.reason == "Rename"


# --- the read-only viewer ---------------------------------------------------------------------------------------------


def test_admin_viewer_is_read_only_and_shows_cairo_time(admin_client):
    client, root = admin_client
    entry = audit.record(A.SETTINGS, actor=root, target_type="setting", target_id="viewer-test")
    listing = client.get("/admin/audit/auditentry/")
    assert listing.status_code == 200 and b"viewer-test" in listing.content
    cairo = entry.time.astimezone(ZoneInfo("Africa/Cairo")).strftime("%Y-%m-%d %H:%M")
    assert cairo.encode() in listing.content
    for params in ("?result=success", "?action=settings.change", "?actor_label=root", "?q=viewer-test"):
        assert client.get("/admin/audit/auditentry/" + params).status_code == 200, params
    assert client.get("/admin/audit/auditentry/add/").status_code == 403
    assert client.get(f"/admin/audit/auditentry/{entry.pk}/delete/").status_code == 403
    detail = client.get(f"/admin/audit/auditentry/{entry.pk}/change/")
    assert detail.status_code == 200 and b"_save" not in detail.content
    assert b"<bdi>viewer-test</bdi>" in detail.content and b"<bdi>viewer-test</bdi>" in listing.content
    audit.record(A.SETTINGS, actor=root, target_type="setting", target_id="json-test", after={"a": "\u0645"})
    pretty = client.get(f"/admin/audit/auditentry/{AuditEntry.objects.get(target_id='json-test').pk}/change/")
    assert b"<pre dir='ltr' style='overflow-x:auto;text-align:left'>" in pretty.content
    assert client.post(f"/admin/audit/auditentry/{entry.pk}/change/", {"reason": "x"}).status_code == 403
    assert AuditEntry.objects.get(pk=entry.pk).reason == ""


def test_admin_viewer_is_hidden_from_non_owner_staff():
    staff = StaffFactory()
    client = Client()
    client.force_login(staff)
    assert client.get("/admin/audit/auditentry/").status_code == 403
