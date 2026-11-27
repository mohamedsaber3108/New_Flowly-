"""Permission matrix (FL-07): every team, admin and customer route against every kind of caller.

Tests only. A case that fails on current code is marked xfail(strict=True) with the reason, never fixed here.
Callers: no auth, customer, viewer, staff, owner, shared ADMIN_TOKEN, soft-deleted staff.
"""

from io import BytesIO

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.audit.models import AuditEntry
from apps.leads.models import Request
from tests.factories import PASSWORD, OwnerFactory, RequestFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Another-Str0ng-pw!9"


def tiny_png():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("me.png", buffer.getvalue(), content_type="image/png")


DENIED = (401, 403)
TEAM_MESSAGE = "Team access is required."  # v1 403 body message
LEGACY_FORBIDDEN = "Forbidden"  # legacy /api/* 403 body: {"error": "Forbidden"}
PATCH_BODY = {"status": "confirmed"}

# (id, method, url template, kind, body)
ROUTES = [
    ("legacy-list-get", "get", "/api/admin/requests", "team_read", None),
    ("legacy-detail-patch", "patch", "/api/admin/requests/{ref}", "team_write", PATCH_BODY),
    ("v1-list-get", "get", "/api/v1/admin/requests/", "team_read", None),
    ("v1-detail-get", "get", "/api/v1/admin/requests/{ref}/", "team_read", None),
    ("v1-detail-patch", "patch", "/api/v1/admin/requests/{ref}/", "team_write", PATCH_BODY),
    ("v1-stats-get", "get", "/api/v1/admin/stats/", "team_read", None),
    ("v1-dashboard-get", "get", "/api/v1/dashboard/", "customer", None),
    ("v1-mine-get", "get", "/api/v1/requests/mine/", "customer", None),
    ("v1-mine-detail-get", "get", "/api/v1/requests/mine/{ref}/", "customer", None),
    ("v1-me-get", "get", "/api/v1/users/me/", "customer", None),
    ("v1-me-patch", "patch", "/api/v1/users/me/", "customer", {"first_name": "Changed"}),
]
CALLERS = ["none", "customer", "viewer", "staff", "owner", "admin_token"]

# Expected result per kind: True = must be allowed (not 401/403), 401 or 403 = must be refused with that code.
EXPECT = {
    "team_read": dict(none=401, customer=403, viewer=True, staff=True, owner=True, admin_token=True),
    "team_write": dict(none=401, customer=403, viewer=403, staff=True, owner=True, admin_token=True),
    # Customer routes use JWT only: the shared ADMIN_TOKEN is not a JWT, so it is a clean 401.
    "customer": dict(none=401, customer=True, viewer=True, staff=True, owner=True, admin_token=401),
}


def bearer(user):
    return f"Bearer {AccessToken.for_user(user)}"


@pytest.fixture
def ref():
    return RequestFactory().reference


def auth_header(caller):
    if caller == "none":
        return {}
    if caller == "admin_token":
        return {"HTTP_AUTHORIZATION": f"Bearer {django_settings.ADMIN_TOKEN}"}
    factory = {"customer": UserFactory, "viewer": lambda: UserFactory(role="viewer"), "staff": StaffFactory}
    user = OwnerFactory() if caller == "owner" else factory[caller]()
    return {"HTTP_AUTHORIZATION": bearer(user)}


def call(method, url, body=None, **headers):
    return getattr(APIClient(), method)(url, body, format="json", **headers)


def assert_refusal_message(response, url):
    body = response.json()
    if response.status_code == 403:
        if url.startswith("/api/v1/admin/"):
            assert TEAM_MESSAGE in body["message"]
        elif url.startswith("/api/admin/"):
            assert body["error"] == LEGACY_FORBIDDEN
        else:
            assert body["message"]  # plain, non-empty text, no stack trace
    elif response.status_code == 401:
        assert body.get("message") or body.get("error")


@pytest.mark.parametrize("caller", CALLERS)
@pytest.mark.parametrize("route", ROUTES, ids=[r[0] for r in ROUTES])
def test_matrix(route, caller, ref, settings):
    _, method, template, kind, body = route
    url = template.format(ref=ref)
    # The shared key only works when the owner switches it on (see test_shared_key_off_* for the default).
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    response = call(method, url, body, **auth_header(caller))
    expected = EXPECT[kind][caller]
    if expected is True:
        assert response.status_code not in DENIED, (url, caller, response.status_code, response.content[:200])
    else:
        assert response.status_code == expected, (url, caller, response.status_code)
        assert_refusal_message(response, url)


@pytest.mark.parametrize("url", ["/api/admin/requests", "/api/v1/admin/requests/", "/api/v1/admin/stats/"])
def test_allowed_team_reads_return_200(url, settings):
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    for caller in ("viewer", "staff", "owner", "admin_token"):
        assert call("get", url, **auth_header(caller)).status_code == 200, (url, caller)


def test_no_auth_delete_account_is_401():
    assert call("delete", "/api/v1/users/me/", {"password": "x"}).status_code == 401


# --- soft-deleted accounts --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTES, ids=[r[0] for r in ROUTES])
def test_deleted_staff_is_refused_with_a_valid_old_token(route, ref):
    _, method, template, _, body = route
    deleted = StaffFactory()
    header = {"HTTP_AUTHORIZATION": bearer(deleted)}
    deleted.soft_delete()
    response = call(method, template.format(ref=ref), body, **header)
    assert response.status_code in DENIED


@pytest.mark.parametrize("route", [r for r in ROUTES if r[3] != "customer"], ids=lambda r: r[0])
def test_deleted_team_user_is_403_even_if_authentication_lets_it_through(route, ref):
    """Defence in depth: the permission class itself refuses is_deleted users."""
    _, method, template, _, body = route
    deleted = StaffFactory()
    deleted.soft_delete()
    client = APIClient()
    client.force_authenticate(user=deleted)
    response = getattr(client, method)(template.format(ref=ref), body, format="json")
    assert response.status_code == 403
    assert_refusal_message(response, template)


def test_deleted_user_cannot_delete_or_read_profile():
    user = UserFactory()
    header = {"HTTP_AUTHORIZATION": bearer(user)}
    user.soft_delete()
    assert call("get", "/api/v1/users/me/", **header).status_code in DENIED
    assert call("delete", "/api/v1/users/me/", {"password": "x"}, **header).status_code in DENIED


# --- shared ADMIN_TOKEN rules -----------------------------------------------------------------------------------------

TEAM_URLS = ["/api/admin/requests", "/api/v1/admin/requests/", "/api/v1/admin/stats/"]


@pytest.mark.parametrize("url", TEAM_URLS)
@pytest.mark.parametrize("configured", [None, "", "x" * 31], ids=["unset", "empty", "31-chars"])
def test_unset_or_short_admin_token_never_authenticates(url, configured, settings):
    settings.ALLOW_SHARED_ADMIN_TOKEN = True  # even when allowed, a missing or short key is refused
    settings.ADMIN_TOKEN = configured
    for supplied in (configured or "", "x" * 31, "x" * 32):
        response = call("get", url, HTTP_AUTHORIZATION=f"Bearer {supplied}")
        assert response.status_code == 401, (url, repr(configured), len(supplied))


@pytest.mark.parametrize("url", TEAM_URLS)
def test_admin_token_exactly_32_chars_works_and_wrong_token_does_not(url, settings):
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    settings.ADMIN_TOKEN = "k" * 32
    assert call("get", url, HTTP_AUTHORIZATION="Bearer " + "k" * 32).status_code == 200
    assert call("get", url, HTTP_AUTHORIZATION="Bearer " + "k" * 31 + "z").status_code == 401
    assert call("get", url, HTTP_AUTHORIZATION="Basic " + "k" * 32).status_code == 401


@pytest.mark.parametrize("route", ROUTES, ids=[r[0] for r in ROUTES])
def test_shared_key_off_by_default_is_401_everywhere(route, ref, settings):
    """FL-08: with the default setting, the old key (correct, 39 chars) opens nothing."""
    from django.conf import settings as live_settings

    assert live_settings.ALLOW_SHARED_ADMIN_TOKEN is False
    _, method, template, _, body = route
    response = call(method, template.format(ref=ref), body, **auth_header("admin_token"))
    assert response.status_code == 401, (template, response.status_code)


# --- customers cannot read each other's requests ----------------------------------------------------------------------


def test_customer_cannot_read_another_customers_request():
    owner_of_request = UserFactory()
    other = UserFactory()
    mine = RequestFactory(user=owner_of_request, email=owner_of_request.email)
    header = {"HTTP_AUTHORIZATION": bearer(other)}

    assert call("get", f"/api/v1/requests/mine/{mine.reference}/", **header).status_code in (403, 404)
    listing = call("get", "/api/v1/requests/mine/", **header)
    assert listing.status_code == 200
    assert mine.reference not in listing.content.decode()

    # The owner of the request does see it.
    own = call("get", f"/api/v1/requests/mine/{mine.reference}/", HTTP_AUTHORIZATION=bearer(owner_of_request))
    assert own.status_code == 200


# --- Django admin and account portal ----------------------------------------------------------------------------------


def admin_index():
    return f"/{django_settings.ADMIN_URL}"


def test_django_admin_refuses_anonymous_and_non_staff():
    for user in (None, UserFactory(), UserFactory(role="viewer")):
        client = Client()
        if user:
            client.force_login(user)
        response = client.get(admin_index(), follow=False)
        assert response.status_code == 302 and "login" in response["Location"], user


def test_django_admin_refuses_a_deleted_staff_user():
    staff = StaffFactory()
    staff.soft_delete()
    client = Client()
    client.force_login(staff)  # is_active is False, so the session does not authenticate
    response = client.get(admin_index(), follow=False)
    assert response.status_code == 302 and "login" in response["Location"]


def test_django_admin_allows_staff_and_owner():
    for factory in (StaffFactory, OwnerFactory):
        client = Client()
        client.force_login(factory())
        assert client.get(admin_index()).status_code == 200


def test_account_portal_is_a_public_shell_with_no_account_data():
    """/account/ is the login page (vanilla JS); data only comes from /api/v1, which the matrix above protects."""
    victim = UserFactory(email="portal.victim@example.test")
    response = Client().get("/account/")
    assert response.status_code == 200
    assert victim.email.encode() not in response.content


# --- FL-07b: refusals leak nothing, own-account routes, viewer in the Django admin -------------------


def leak_values():
    """A real request with values that cannot appear in a refusal by accident."""
    req = RequestFactory(
        name="Zainab Leakcheck",
        email="leak.check@example.test",
        organization="Leakcheck Holdings",
        internal_note="Private leakcheck note.",
    )
    return req, [req.reference, req.name, req.email, req.organization, req.internal_note]


@pytest.mark.parametrize("caller", CALLERS)
@pytest.mark.parametrize("route", ROUTES, ids=[r[0] for r in ROUTES])
def test_a_401_or_403_body_never_contains_the_fields_of_a_real_request(route, caller, settings):
    """Finding 4: a refusal says no and nothing about the request it was asked for."""
    _, method, template, _, body = route
    req, secrets = leak_values()
    settings.ALLOW_SHARED_ADMIN_TOKEN = True
    response = call(method, template.format(ref=req.reference), body, **auth_header(caller))
    if response.status_code in DENIED:
        text = response.content.decode()
        # the reference is in the address, so a refusal must not echo it back either
        for secret in secrets:
            assert secret not in text, (template, caller, secret)


def test_refusals_for_a_request_that_belongs_to_another_customer_leak_nothing():
    req, secrets = leak_values()
    other = UserFactory()
    for url in (f"/api/v1/requests/mine/{req.reference}/", "/api/v1/requests/mine/"):
        response = call("get", url, HTTP_AUTHORIZATION=bearer(other))
        for secret in secrets:
            assert secret not in response.content.decode(), (url, secret)


OWN_ACCOUNT_URLS = ["/api/v1/users/me/avatar/", "/api/v1/users/me/change-password/"]


@pytest.mark.parametrize("url", OWN_ACCOUNT_URLS)
def test_avatar_and_change_password_need_a_sign_in(url):
    assert call("post", url, {"current_password": "x", "new_password": "y"}).status_code == 401
    assert call("get", url).status_code in (401, 405)  # no read route; never a 200


@pytest.mark.parametrize("url", OWN_ACCOUNT_URLS)
def test_avatar_and_change_password_are_refused_for_a_deleted_account_with_an_old_token(url):
    user = UserFactory()
    header = {"HTTP_AUTHORIZATION": bearer(user)}
    user.soft_delete()
    assert (
        call("post", url, {"current_password": PASSWORD, "new_password": "Another-Str0ng-pw!"}, **header).status_code
        in DENIED
    )


def test_change_password_changes_only_the_callers_own_account():
    mine, other = UserFactory(), UserFactory()
    other_hash = type(other).objects.get(pk=other.pk).password
    header = {"HTTP_AUTHORIZATION": bearer(mine)}
    wrong = call(
        "post",
        "/api/v1/users/me/change-password/",
        {"current_password": "nope", "new_password": NEW_PASSWORD},
        **header,
    )
    assert wrong.status_code == 400
    done = call(
        "post",
        "/api/v1/users/me/change-password/",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        **header,
    )
    assert done.status_code == 200
    mine.refresh_from_db()
    other.refresh_from_db()
    assert mine.check_password(NEW_PASSWORD) and not mine.check_password(PASSWORD)
    assert other.password == other_hash and other.check_password(PASSWORD)  # nobody else was touched


def test_avatar_upload_changes_only_the_callers_own_account():
    mine, other = UserFactory(), UserFactory()
    header = {"HTTP_AUTHORIZATION": bearer(mine)}
    response = APIClient().post("/api/v1/users/me/avatar/", {"avatar": tiny_png()}, format="multipart", **header)
    assert response.status_code == 200, response.content[:200]
    mine.refresh_from_db()
    other.refresh_from_db()
    assert mine.avatar and not other.avatar
    not_an_image = SimpleUploadedFile("x.png", b"this is text, not a picture", content_type="image/png")
    bad = APIClient().post("/api/v1/users/me/avatar/", {"avatar": not_an_image}, format="multipart", **header)
    assert bad.status_code == 400


def test_deleting_the_account_is_a_soft_delete_and_the_user_cannot_sign_in_after():
    user = UserFactory()
    header = {"HTTP_AUTHORIZATION": bearer(user)}
    assert call("delete", "/api/v1/users/me/", {"password": "wrong"}, **header).status_code == 400  # needs the password
    user.refresh_from_db()
    assert not user.is_deleted
    done = call("delete", "/api/v1/users/me/", {"password": PASSWORD}, **header)
    assert done.status_code == 200
    user.refresh_from_db()
    assert user.is_deleted and not user.is_active and user.deleted_at  # the row stays, for the request history
    assert AuditEntry.objects.filter(action="user.delete", target_id=str(user.pk)).exists()
    login = call("post", "/api/v1/auth/login/", {"email": user.email, "password": PASSWORD})
    assert login.status_code in DENIED and "access" not in login.content.decode()
    assert call("get", "/api/v1/users/me/", **header).status_code in DENIED  # the old token is dead too


def viewer_client(*, with_permissions):
    """A team member with the viewer role and is_staff=True. `with_permissions` also puts them in a group that
    has every permission on the leads app (someone may do that by hand in the admin)."""
    viewer = UserFactory(role="viewer", is_staff=True)
    if with_permissions:
        group = Group.objects.create(name="Everything on leads")
        group.permissions.set(Permission.objects.filter(content_type__app_label="leads"))
        viewer.groups.add(group)
    client = Client()
    client.force_login(viewer)
    return client, viewer


def test_a_viewer_with_is_staff_can_open_the_admin_but_not_the_request_data_by_default():
    req = RequestFactory()
    client, _ = viewer_client(with_permissions=False)
    assert client.get(admin_index()).status_code == 200
    assert client.get("/admin/leads/request/").status_code == 403
    assert client.post(f"/admin/leads/request/{req.pk}/change/", {"status": "confirmed"}).status_code == 403
    req.refresh_from_db()
    assert req.status == "pending_review"


def test_a_viewer_cannot_change_add_or_delete_in_the_django_admin_even_with_every_permission_granted():
    """ADMIN.md s.3: the viewer (Analyst) is read-only. The refusal is on the server, so a group that grants write
    permissions does not change it."""
    req = RequestFactory()
    other_user = UserFactory()
    client, viewer = viewer_client(with_permissions=True)
    assert not any(viewer.has_perm(f"leads.{kind}_request") for kind in ("add", "change", "delete"))
    assert viewer.has_perm("leads.view_request")  # looking is allowed
    listing = client.get("/admin/leads/request/")
    assert listing.status_code == 200 and req.reference.encode() in listing.content
    detail = client.get(f"/admin/leads/request/{req.pk}/change/")
    assert detail.status_code == 200 and b'name="_save"' not in detail.content  # no save button
    changed = client.post(f"/admin/leads/request/{req.pk}/change/", {"status": "confirmed", "internal_note": "x"})
    assert changed.status_code == 403
    assert client.get("/admin/leads/request/add/").status_code == 403
    assert client.post(f"/admin/leads/request/{req.pk}/delete/", {"post": "yes"}).status_code == 403
    # the list actions that change requests are refused too
    for action_name in ("mark_confirmed", "mark_in_review", "mark_declined"):
        client.post("/admin/leads/request/", {"action": action_name, "_selected_action": [str(req.pk)]})
    users = client.post(
        f"/admin/accounts/user/{other_user.pk}/change/", {"role": "owner", "email": other_user.email, "is_active": "on"}
    )
    assert users.status_code == 403
    req.refresh_from_db()
    other_user.refresh_from_db()
    assert req.status == "pending_review" and Request.objects.filter(pk=req.pk).exists()
    assert other_user.role == "customer"


def test_the_mark_actions_are_not_offered_to_a_viewer_but_the_csv_export_still_is():
    client, _ = viewer_client(with_permissions=True)
    RequestFactory()
    page = client.get("/admin/leads/request/").content.decode()
    assert "Export selected as CSV" in page  # reading is allowed
    assert "Mark as confirmed" not in page and "Mark as in review" not in page and "Mark as declined" not in page


def test_staff_and_the_owner_keep_the_mark_actions_when_they_may_change():
    req = RequestFactory()
    root = UserFactory(is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(root)
    page = client.get("/admin/leads/request/").content.decode()
    assert "Mark as confirmed" in page
    client.post("/admin/leads/request/", {"action": "mark_confirmed", "_selected_action": [str(req.pk)]})
    req.refresh_from_db()
    assert req.status == "confirmed"
