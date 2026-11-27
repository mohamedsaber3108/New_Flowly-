"""FL-22: staff sign in with httpOnly cookies (and a CSRF header), not with tokens a page script can read.

Customers are unchanged: tokens in the body, bearer header.
"""

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts import services
from apps.accounts.session_cookie import ACCESS_COOKIE, REFRESH_COOKIE
from tests.factories import PASSWORD, OwnerFactory, RequestFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db

V1 = "/api/v1"
ROOT = Path(__file__).resolve().parents[3]


def browser():
    """A client that keeps cookies and, like a browser session, is checked for CSRF."""
    return APIClient(enforce_csrf_checks=True)


def sign_in(client, user, **extra):
    return client.post(f"{V1}/auth/login/", {"email": user.email, "password": PASSWORD}, format="json", **extra)


def csrf_header(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


# --- sign-in ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("factory", [StaffFactory, OwnerFactory])
def test_staff_sign_in_sets_http_only_cookies_and_returns_no_token(factory):
    user = factory()
    client = browser()
    response = sign_in(client, user)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["session"] == "cookie" and body["user"]["email"] == user.email
    assert "access" not in body and "refresh" not in body
    access, refresh = response.cookies[ACCESS_COOKIE], response.cookies[REFRESH_COOKIE]
    for cookie in (access, refresh):
        assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Strict"
    assert access["path"] == "/api/" and refresh["path"] == "/api/v1/auth/"  # the refresh cookie goes nowhere else
    assert int(access["max-age"]) == 15 * 60 and int(refresh["max-age"]) == 1800  # idle limit, like the admin
    assert body["session_seconds"] == 1800
    assert int(AccessToken(access.value)["user_id"]) == user.pk
    assert int(RefreshToken(refresh.value)["user_id"]) == user.pk
    assert not response.cookies["csrftoken"]["httponly"]  # the page must be able to read it to send the header
    assert response.cookies["csrftoken"]["samesite"] == "Strict"


def test_a_viewer_gets_the_cookie_too():
    response = sign_in(browser(), UserFactory(role="viewer", is_staff=True))
    assert ACCESS_COOKIE in response.cookies and "access" not in response.json()["data"]


def test_customers_are_unchanged_tokens_in_the_body_and_no_staff_cookie():
    customer = UserFactory()
    response = sign_in(browser(), customer)
    data = response.json()["data"]
    assert response.status_code == 200 and data["access"] and data["refresh"]
    assert ACCESS_COOKIE not in response.cookies and REFRESH_COOKIE not in response.cookies
    me = APIClient().get(f"{V1}/users/me/", HTTP_AUTHORIZATION=f"Bearer {data['access']}")
    assert me.status_code == 200


# --- using the cookie ------------------------------------------------------------------------------------------------


def test_the_cookie_signs_in_team_routes_and_a_reading_call_needs_no_csrf_header():
    client = browser()
    sign_in(client, StaffFactory())
    RequestFactory()
    assert client.get(f"{V1}/admin/requests/").status_code == 200
    assert client.get("/api/admin/requests").status_code == 200


def test_a_change_with_the_cookie_but_without_the_csrf_header_is_refused_and_changes_nothing():
    req = RequestFactory()
    client = browser()
    sign_in(client, StaffFactory())
    url = f"{V1}/admin/requests/{req.reference}/"
    refused = client.patch(url, {"status": "in_review"}, format="json")
    assert refused.status_code == 403 and "CSRF" in refused.content.decode()
    wrong = client.patch(url, {"status": "in_review"}, format="json", HTTP_X_CSRFTOKEN="not-the-token")
    assert wrong.status_code == 403
    req.refresh_from_db()
    assert req.status == "pending_review"
    allowed = client.patch(url, {"status": "in_review"}, format="json", **csrf_header(client))
    assert allowed.status_code == 200
    req.refresh_from_db()
    assert req.status == "in_review"


def test_the_old_team_routes_need_the_csrf_header_too():
    req = RequestFactory()
    client = browser()
    sign_in(client, StaffFactory())
    url = f"/api/admin/requests/{req.reference}"
    assert client.patch(url, {"status": "in_review"}, format="json").status_code == 403
    assert client.patch(url, {"status": "in_review"}, format="json", **csrf_header(client)).status_code == 200


def test_an_expired_or_bad_cookie_is_a_401_not_a_pass():
    client = browser()
    client.cookies[ACCESS_COOKIE] = "garbage"
    assert client.get(f"{V1}/admin/requests/").status_code == 401


# --- the bearer header for staff ---------------------------------------------------------------------


def test_a_staff_bearer_token_is_refused_unless_the_setting_allows_it(settings):
    staff = StaffFactory()
    header = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(staff)}"}
    settings.ALLOW_STAFF_BEARER = False
    refused = APIClient().get(f"{V1}/admin/requests/", **header)
    assert refused.status_code == 401 and "browser session" in refused.content.decode()
    customer_header = {"HTTP_AUTHORIZATION": f"Bearer {AccessToken.for_user(UserFactory())}"}
    assert APIClient().get(f"{V1}/users/me/", **customer_header).status_code == 200  # customers are not affected
    settings.ALLOW_STAFF_BEARER = True
    assert APIClient().get(f"{V1}/admin/requests/", **header).status_code == 200


def test_the_staff_bearer_setting_is_off_by_default():
    from config.settings import base

    assert base.ALLOW_STAFF_BEARER is False and base.STAFF_COOKIE_SECURE is True


# --- refresh ---------------------------------------------------------------------------------------------------------


def test_refresh_with_the_cookie_rotates_both_cookies_and_returns_no_token():
    client = browser()
    first = sign_in(client, StaffFactory())
    old_refresh = first.cookies[REFRESH_COOKIE].value
    assert client.post(f"{V1}/auth/token/refresh/", {}, format="json").status_code == 403  # no CSRF header
    response = client.post(f"{V1}/auth/token/refresh/", {}, format="json", **csrf_header(client))
    assert response.status_code == 200
    assert "access" not in response.json()["data"] and "refresh" not in response.json()["data"]
    new_refresh = response.cookies[REFRESH_COOKIE].value
    assert new_refresh != old_refresh and response.cookies[ACCESS_COOKIE]["httponly"]
    # the old refresh token was blacklisted by the rotation
    assert APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": old_refresh}, format="json").status_code == 401


def test_refresh_with_the_cookie_keeps_the_mfa_rule(settings):
    staff = StaffFactory()
    client = browser()
    sign_in(client, staff)  # signed in without a second factor (the rule was off)
    settings.REQUIRE_STAFF_MFA = True
    response = client.post(f"{V1}/auth/token/refresh/", {}, format="json", **csrf_header(client))
    assert response.status_code == 401 and ACCESS_COOKIE not in response.cookies


def test_a_token_sent_in_the_body_still_refreshes_for_token_clients():
    customer = UserFactory()
    refresh = sign_in(browser(), customer).json()["data"]["refresh"]
    response = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert response.status_code == 200 and response.json()["data"]["access"]


def test_a_team_refresh_token_in_the_body_is_refused_unless_the_setting_allows_it(settings):
    staff = StaffFactory()
    refresh = services.issue_tokens(staff, team_session=True)["refresh"]  # a token from a real team sign-in
    settings.ALLOW_STAFF_BEARER = False
    refused = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert refused.status_code == 401 and "browser session" in refused.content.decode()
    assert "access" not in refused.content.decode()  # no new token in JSON
    # nothing was consumed: the same token was not rotated or blacklisted by the refusal
    settings.ALLOW_STAFF_BEARER = True
    assert APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json").status_code == 200


def test_the_body_refusal_does_not_touch_customers_or_bad_tokens(settings):
    settings.ALLOW_STAFF_BEARER = False
    refresh = str(RefreshToken.for_user(UserFactory()))
    assert APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json").status_code == 200
    bad = APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": "garbage"}, format="json")
    assert bad.status_code == 401 and "browser session" not in bad.content.decode()


# --- old tokens after the deploy -----------------------------------------------------------------------------------


def run_revoke(*args):
    out = StringIO()
    call_command("revoke_staff_tokens", *args, stdout=out)
    return out.getvalue()


def test_revoke_staff_tokens_blacklists_team_tokens_only_and_can_run_again():
    staff, owner, viewer, customer = StaffFactory(), OwnerFactory(), UserFactory(role="viewer"), UserFactory()
    old = {u: [str(RefreshToken.for_user(u)), str(RefreshToken.for_user(u))] for u in (staff, owner, viewer, customer)}
    first = run_revoke()
    assert "refresh tokens revoked 6" in first and "team accounts 3" in first
    for user in (staff, owner, viewer):
        for token in old[user]:
            assert APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": token}, format="json").status_code == 401
    assert (
        APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": old[customer][0]}, format="json").status_code == 200
    )
    assert "refresh tokens revoked 0" in run_revoke()  # run again: nothing left to do, nothing breaks
    assert not any(token in first for tokens in old.values() for token in tokens)  # counts only


def test_revoke_staff_tokens_before_leaves_newer_sessions_alone():
    staff = StaffFactory()
    client = browser()
    sign_in(client, staff)  # a cookie session started after the deploy
    assert "refresh tokens revoked 0" in run_revoke("--before", "2020-01-01T00:00:00+00:00")
    assert client.post(f"{V1}/auth/token/refresh/", {}, format="json", **csrf_header(client)).status_code == 200
    with pytest.raises(CommandError):
        run_revoke("--before", "yesterday")


# --- sign out --------------------------------------------------------------------------------------------------------


def test_sign_out_clears_both_cookies_and_blacklists_the_refresh_token():
    client = browser()
    refresh = sign_in(client, StaffFactory()).cookies[REFRESH_COOKIE].value
    assert client.post(f"{V1}/auth/logout/", {}, format="json").status_code == 403  # no CSRF header: nothing happens
    response = client.post(f"{V1}/auth/logout/", {}, format="json", **csrf_header(client))
    assert response.status_code == 200
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        assert response.cookies[name].value == "" and int(response.cookies[name]["max-age"]) == 0
    assert APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json").status_code == 401


def test_sign_out_still_works_after_the_access_cookie_has_expired():
    client = browser()
    refresh = sign_in(client, StaffFactory()).cookies[REFRESH_COOKIE].value
    del client.cookies[ACCESS_COOKIE]  # the browser dropped it after 15 minutes
    response = client.post(f"{V1}/auth/logout/", {}, format="json", **csrf_header(client))
    assert response.status_code == 200 and response.cookies[REFRESH_COOKIE].value == ""
    assert APIClient().post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json").status_code == 401


def test_a_customer_sign_out_with_a_token_still_works_and_an_unsigned_call_is_401():
    customer = UserFactory()
    tokens = sign_in(browser(), customer).json()["data"]
    header = {"HTTP_AUTHORIZATION": f"Bearer {tokens['access']}"}
    assert (
        APIClient().post(f"{V1}/auth/logout/", {"refresh": tokens["refresh"]}, format="json", **header).status_code
        == 200
    )
    assert APIClient().post(f"{V1}/auth/logout/", {}, format="json").status_code == 401


# --- the pages ---------------------------------------------------------------------------------------


def test_the_team_console_keeps_no_staff_token_and_sends_the_csrf_header():
    source = (ROOT / "frontend" / "components" / "TeamConsole.tsx").read_text()
    assert "localStorage" not in source and "sessionStorage" not in source
    assert "X-CSRFToken" in source and "credentials:'same-origin'" in source
    assert "access.current" not in source and "refreshToken.current" not in source
    assert "/api/v1/auth/token/refresh/" in source and "/api/v1/auth/logout/" in source


def test_the_portal_does_not_store_a_staff_session():
    script = (ROOT / "backend" / "static" / "account" / "portal.js").read_text()
    assert "j.data.session === 'cookie'" in script and "X-CSRFToken" in script
