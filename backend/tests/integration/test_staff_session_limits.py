"""FL-22b: team cookie sessions end after 30 minutes idle or 8 hours in all, on the server.

The clock the limits use (`session_limits._now`) is replaced in these tests, so a day passes in a moment. Signing in
and the token lifetimes use the real clock. Customers' sessions are not limited.
"""

from pathlib import Path

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts import services, session_limits
from apps.accounts.session_cookie import ACCESS_COOKIE, REFRESH_COOKIE
from tests.factories import PASSWORD, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db

V1 = "/api/v1"
MINUTE, HOUR = 60, 3600
ROOT = Path(__file__).resolve().parents[3]


class Clock:
    def __init__(self, monkeypatch):
        self.now = session_limits._now()
        monkeypatch.setattr(session_limits, "_now", lambda: self.now)

    def move(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    return Clock(monkeypatch)


def browser():
    return APIClient(enforce_csrf_checks=True)


def sign_in(client, user):
    return client.post(f"{V1}/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")


def csrf(client):
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def team_read(client):
    return client.get(f"{V1}/admin/requests/")


def refresh(client):
    return client.post(f"{V1}/auth/token/refresh/", {}, format="json", **csrf(client))


def code_of(response):
    return response.json()["errors"]["code"]


def test_a_team_sign_in_puts_the_session_claims_in_both_tokens_and_customers_get_none(clock):
    staff_client = browser()
    response = sign_in(staff_client, StaffFactory())
    for token in (
        RefreshToken(response.cookies[REFRESH_COOKIE].value),
        AccessToken(response.cookies[ACCESS_COOKIE].value),
    ):
        assert abs(token["auth_time"] - clock.now) < 5 and len(token["sid"]) == 32
    customer = sign_in(browser(), UserFactory()).json()["data"]
    assert "auth_time" not in AccessToken(customer["access"]) and "sid" not in RefreshToken(customer["refresh"])


def test_activity_keeps_a_session_alive_past_thirty_minutes_in_all(clock):
    client = browser()
    sign_in(client, StaffFactory())
    for _ in range(4):  # a request every 25 minutes: 100 minutes in all, never idle for 30
        clock.move(25 * MINUTE)
        assert team_read(client).status_code == 200
    clock.move(25 * MINUTE)
    assert refresh(client).status_code == 200  # a refresh counts as activity too


def test_thirty_minutes_without_a_request_ends_the_session_with_session_idle(clock):
    client = browser()
    sign_in(client, StaffFactory())
    clock.move(31 * MINUTE)
    ended = team_read(client)
    assert ended.status_code == 401 and code_of(ended) == "session_idle"
    assert "30 minutes" in ended.json()["message"]
    refused = refresh(client)
    assert refused.status_code == 401 and code_of(refused) == "session_idle"
    assert ACCESS_COOKIE not in refused.cookies  # no new cookie was given


def test_the_old_team_api_says_the_same_in_its_own_format(clock):
    client = browser()
    sign_in(client, StaffFactory())
    clock.move(31 * MINUTE)
    ended = client.get("/api/admin/requests")
    assert ended.status_code == 401 and ended.json()["code"] == "session_idle"


def test_a_session_that_is_still_busy_ends_after_eight_hours_with_session_expired(clock):
    client = browser()
    sign_in(client, StaffFactory())
    for _ in range(23):  # a request every 20 minutes up to 7 hours 40 minutes
        clock.move(20 * MINUTE)
        assert team_read(client).status_code == 200
    clock.move(21 * MINUTE)  # 8 hours 1 minute after the sign-in, 21 minutes after the last request
    ended = team_read(client)
    assert ended.status_code == 401 and code_of(ended) == "session_expired"
    assert "8 hours" in ended.json()["message"]
    refused = refresh(client)
    assert refused.status_code == 401 and code_of(refused) == "session_expired"


def test_the_last_seen_time_moves_forward_at_most_once_a_minute(clock):
    client = browser()
    response = sign_in(client, StaffFactory())
    key = f"staff-session:{RefreshToken(response.cookies[REFRESH_COOKIE].value)['sid']}:seen"
    started = cache.get(key)
    clock.move(30)
    assert team_read(client).status_code == 200
    assert cache.get(key) == started  # 30 seconds later: not written again
    clock.move(40)
    assert team_read(client).status_code == 200
    assert cache.get(key) == int(clock.now)  # 70 seconds after the start: moved forward


def test_a_refresh_keeps_the_session_claims_and_the_mfa_rule_still_applies(clock, settings):
    staff = StaffFactory()
    client = browser()
    first = sign_in(client, staff)
    before = RefreshToken(first.cookies[REFRESH_COOKIE].value)
    clock.move(5 * MINUTE)
    rotated = refresh(client)
    assert rotated.status_code == 200
    after = RefreshToken(rotated.cookies[REFRESH_COOKIE].value)
    assert (after["auth_time"], after["sid"]) == (before["auth_time"], before["sid"])  # the 8 hours do not restart
    assert after["jti"] != before["jti"]
    settings.REQUIRE_STAFF_MFA = True  # signed in without a second factor: the PR #8 rule refuses the refresh
    assert refresh(client).status_code == 401


def test_a_team_token_without_the_session_claims_is_refused_as_expired():
    """Tokens from before this change (7-day refresh tokens, 15-minute access cookies) must not live on."""
    staff = StaffFactory()
    old = RefreshToken.for_user(staff)
    client = browser()
    client.cookies[REFRESH_COOKIE] = str(old)
    client.cookies["csrftoken"] = "x" * 32
    refused = client.post(f"{V1}/auth/token/refresh/", {}, format="json", HTTP_X_CSRFTOKEN="x" * 32)
    assert refused.status_code == 401 and code_of(refused) == "session_expired"
    client.cookies[ACCESS_COOKIE] = str(old.access_token)
    assert code_of(client.get(f"{V1}/admin/requests/")) == "session_expired"


def test_customers_are_not_limited_by_the_clock(clock):
    customer = UserFactory()
    tokens = sign_in(browser(), customer).json()["data"]
    clock.move(10 * HOUR)
    api = APIClient()
    assert api.post(f"{V1}/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 200
    assert api.get(f"{V1}/users/me/", HTTP_AUTHORIZATION=f"Bearer {tokens['access']}").status_code == 200


def test_a_bearer_token_of_a_team_session_is_limited_too_when_bearer_is_allowed(clock, settings):
    settings.ALLOW_STAFF_BEARER = True
    staff = StaffFactory()
    access = services.issue_tokens(staff, team_session=True)["access"]
    header = {"HTTP_AUTHORIZATION": f"Bearer {access}"}
    assert APIClient().get(f"{V1}/admin/requests/", **header).status_code == 200
    clock.move(31 * MINUTE)
    assert code_of(APIClient().get(f"{V1}/admin/requests/", **header)) == "session_idle"


def test_the_team_console_tells_the_two_endings_apart():
    source = (ROOT / "frontend" / "components" / "TeamConsole.tsx").read_text()
    assert "session_idle" in source and "session_expired" in source
