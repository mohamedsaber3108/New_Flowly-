"""Permission matrix (FL-07): every team, admin and customer route against every kind of caller.

Tests only. A case that fails on current code is marked xfail(strict=True) with the reason, never fixed here.
Callers: no auth, customer, viewer, staff, owner, shared ADMIN_TOKEN, soft-deleted staff.
"""

import pytest
from django.conf import settings as django_settings
from django.test import Client
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from tests.factories import OwnerFactory, RequestFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db

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
def test_matrix(route, caller, ref):
    _, method, template, kind, body = route
    url = template.format(ref=ref)
    response = call(method, url, body, **auth_header(caller))
    expected = EXPECT[kind][caller]
    if expected is True:
        assert response.status_code not in DENIED, (url, caller, response.status_code, response.content[:200])
    else:
        assert response.status_code == expected, (url, caller, response.status_code)
        assert_refusal_message(response, url)


@pytest.mark.parametrize("url", ["/api/admin/requests", "/api/v1/admin/requests/", "/api/v1/admin/stats/"])
def test_allowed_team_reads_return_200(url):
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
    settings.ADMIN_TOKEN = configured
    for supplied in (configured or "", "x" * 31, "x" * 32):
        response = call("get", url, HTTP_AUTHORIZATION=f"Bearer {supplied}")
        assert response.status_code == 401, (url, repr(configured), len(supplied))


@pytest.mark.parametrize("url", TEAM_URLS)
def test_admin_token_exactly_32_chars_works_and_wrong_token_does_not(url, settings):
    settings.ADMIN_TOKEN = "k" * 32
    assert call("get", url, HTTP_AUTHORIZATION="Bearer " + "k" * 32).status_code == 200
    assert call("get", url, HTTP_AUTHORIZATION="Bearer " + "k" * 31 + "z").status_code == 401
    assert call("get", url, HTTP_AUTHORIZATION="Basic " + "k" * 32).status_code == 401


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
