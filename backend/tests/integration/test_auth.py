import re
from unittest import mock

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import User
from tests.factories import PASSWORD, UserFactory

pytestmark = pytest.mark.django_db
V1 = "/api/v1"
NEW = {
    "email": "New.User@Example.test",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
    "first_name": "New",
    "last_name": "User",
}


def assert_envelope(response, success):
    body = response.json()
    assert set(body) == {"success", "data", "message", "errors"}
    assert body["success"] is success
    return body


def verify_link_from_mail():
    text = mail.outbox[-1].body
    return re.search(r"/api/v1/auth/verify-email/[^/\s]+/", text).group(0)


# --- register / verify / login -----------------------------------------------


def test_register_creates_customer_and_sends_verification(api):
    r = api.post(f"{V1}/auth/register/", NEW, format="json")
    body = assert_envelope(r, True)
    assert r.status_code == 201
    assert body["data"]["email"] == "new.user@example.test" and body["data"]["role"] == "customer"
    assert "password" not in str(body)
    assert len(mail.outbox) == 1 and "Verify" in mail.outbox[0].subject


def test_register_validation_errors(api):
    r = api.post(f"{V1}/auth/register/", {"email": "bad", "password": "123"}, format="json")
    body = assert_envelope(r, False)
    assert r.status_code == 400 and "email" in body["errors"]
    weak = api.post(f"{V1}/auth/register/", {"email": "ok@example.test", "password": "123"}, format="json")
    assert weak.status_code == 400 and "password" in str(weak.json()["errors"]).lower()


def test_register_duplicate_email_conflict_message(api):
    UserFactory(email="new.user@example.test")
    r = api.post(f"{V1}/auth/register/", NEW, format="json")
    assert r.status_code == 400 and "already exists" in str(r.json()["errors"])


def test_login_blocked_until_email_verified_then_works(api):
    api.post(f"{V1}/auth/register/", NEW, format="json")
    r = api.post(f"{V1}/auth/login/", {"email": NEW["email"], "password": PASSWORD}, format="json")
    assert r.status_code == 403 and r.json()["errors"]["code"] == "email_not_verified"

    verify = api.get(verify_link_from_mail(), HTTP_ACCEPT="application/json")
    assert verify.status_code == 200 and assert_envelope(verify, True)

    r = api.post(f"{V1}/auth/login/", {"email": NEW["email"], "password": PASSWORD}, format="json")
    body = assert_envelope(r, True)
    assert r.status_code == 200
    assert {"access", "refresh", "user"} <= set(body["data"])
    assert body["data"]["user"]["email_verified"] is True


def test_verify_email_browser_redirects_and_bad_key(api):
    api.post(f"{V1}/auth/register/", NEW, format="json")
    r = api.get(verify_link_from_mail(), HTTP_ACCEPT="text/html")
    assert r.status_code == 302 and r["Location"].endswith("/account/?verified=1")
    bad = api.get(f"{V1}/auth/verify-email/garbage/", HTTP_ACCEPT="application/json")
    assert bad.status_code == 400
    assert api.get(f"{V1}/auth/verify-email/garbage/", HTTP_ACCEPT="text/html")["Location"].endswith("verified=0")


def test_verification_links_earlier_anonymous_requests(api, payload):
    from apps.leads.models import Request

    api.post("/api/requests", payload, format="json")
    api.post(f"{V1}/auth/register/", {**NEW, "email": payload["email"]}, format="json")
    mail.outbox.clear()
    mail_user = User.objects.get(email=payload["email"])
    from apps.accounts import services

    services.send_verification_email(mail_user)
    api.get(verify_link_from_mail(), HTTP_ACCEPT="application/json")
    assert Request.objects.get(email=payload["email"]).user == mail_user


def test_resend_verification_never_reveals_accounts(api):
    UserFactory(email="exists@example.test", verified=False)
    a = api.post(f"{V1}/auth/resend-verification/", {"email": "exists@example.test"}, format="json")
    b = api.post(f"{V1}/auth/resend-verification/", {"email": "ghost@example.test"}, format="json")
    assert a.status_code == b.status_code == 200 and a.json()["message"] == b.json()["message"]
    assert len(mail.outbox) == 1


def test_login_wrong_password_is_401(api, user):
    r = api.post(f"{V1}/auth/login/", {"email": user.email, "password": "nope"}, format="json")
    assert r.status_code == 401 and assert_envelope(r, False)["message"] == "Invalid email or password."


def test_login_missing_fields_is_400(api):
    assert api.post(f"{V1}/auth/login/", {}, format="json").status_code == 400


def test_login_deleted_and_suspended_accounts(api):
    gone = UserFactory()
    gone.soft_delete()
    assert api.post(f"{V1}/auth/login/", {"email": gone.email, "password": PASSWORD}, format="json").status_code == 401
    suspended = UserFactory(status="suspended")
    assert (
        api.post(f"{V1}/auth/login/", {"email": suspended.email, "password": PASSWORD}, format="json").status_code
        == 403
    )


def test_login_throttled(api, user, settings):
    from rest_framework.throttling import ScopedRateThrottle

    with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth_login": "2/min"}):
        codes = [
            api.post(f"{V1}/auth/login/", {"email": user.email, "password": "bad"}, format="json").status_code
            for _ in range(4)
        ]
    assert codes[:2] == [401, 401] and codes[2:] == [429, 429]


# --- tokens ---------------------------------------------------------------


def test_token_refresh_rotates_and_old_token_is_blacklisted(api, user):
    refresh = str(RefreshToken.for_user(user))
    r = api.post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json")
    body = assert_envelope(r, True)
    assert r.status_code == 200 and body["data"]["access"] and body["data"]["refresh"] != refresh
    again = api.post(f"{V1}/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert again.status_code == 401


def test_logout_blacklists_refresh_token(api, user):
    refresh = RefreshToken.for_user(user)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    r = api.post(f"{V1}/auth/logout/", {"refresh": str(refresh)}, format="json")
    assert r.status_code == 200
    api.credentials()
    assert api.post(f"{V1}/auth/token/refresh/", {"refresh": str(refresh)}, format="json").status_code == 401
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    assert api.post(f"{V1}/auth/logout/", {"refresh": "junk"}, format="json").status_code == 400


# --- guards ---------------------------------------------------------------


def test_jwt_missing_is_401_with_envelope(api):
    r = api.get(f"{V1}/users/me/")
    assert r.status_code == 401 and assert_envelope(r, False)


def test_jwt_invalid_and_expired_are_401(api, user):
    api.credentials(HTTP_AUTHORIZATION="Bearer garbage")
    assert api.get(f"{V1}/users/me/").status_code == 401
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=-__import__("datetime").timedelta(minutes=1))
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get(f"{V1}/users/me/").status_code == 401


def test_wrong_role_is_403(api, user):
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    r = api.get(f"{V1}/admin/requests/")
    assert r.status_code == 403 and assert_envelope(r, False)


def test_deleted_user_token_is_rejected(api, user):
    token = RefreshToken.for_user(user).access_token
    user.soft_delete()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get(f"{V1}/users/me/").status_code == 401


# --- password reset ------------------------------------------------------


def test_password_reset_flow(api, user):
    r = api.post(f"{V1}/auth/password/reset/", {"email": user.email}, format="json")
    assert r.status_code == 200 and len(mail.outbox) == 1
    link = re.search(r"/accounts/reset/([^/]+)/([^/\s]+)/", mail.outbox[0].body)
    uid, token = link.group(1), link.group(2)

    weak = api.post(
        f"{V1}/auth/password/reset/confirm/", {"uid": uid, "token": token, "new_password": "123"}, format="json"
    )
    assert weak.status_code == 400
    ok = api.post(
        f"{V1}/auth/password/reset/confirm/",
        {"uid": uid, "token": token, "new_password": "Brand-New-Pass1!"},
        format="json",
    )
    assert ok.status_code == 200
    again = api.post(
        f"{V1}/auth/password/reset/confirm/",
        {"uid": uid, "token": token, "new_password": "Another-Pass1!x"},
        format="json",
    )
    assert again.status_code == 400  # token is single use
    login = api.post(f"{V1}/auth/login/", {"email": user.email, "password": "Brand-New-Pass1!"}, format="json")
    assert login.status_code == 200


def test_password_reset_unknown_email_looks_identical(api):
    r = api.post(f"{V1}/auth/password/reset/", {"email": "ghost@example.test"}, format="json")
    assert r.status_code == 200 and len(mail.outbox) == 0


def test_built_in_reset_page_renders(api, user):
    api.post(f"{V1}/auth/password/reset/", {"email": user.email}, format="json")
    path = re.search(r"/accounts/reset/[^\s]+", mail.outbox[0].body).group(0)
    page = api.get(path, follow=True)
    assert page.status_code == 200 and b"new_password1" in page.content


# --- Google ---------------------------------------------------------------


def fake_google(claims, token_status=200, info_status=200):
    def post(url, **kwargs):
        return mock.Mock(status_code=token_status, json=lambda: {"id_token": "tok"})

    def get(url, **kwargs):
        return mock.Mock(status_code=info_status, json=lambda: claims)

    return mock.patch("apps.accounts.services.requests.post", post), mock.patch(
        "apps.accounts.services.requests.get", get
    )


CLAIMS = {
    "aud": "test-google-client-id",
    "sub": "g-123",
    "email": "gina@example.test",
    "email_verified": "true",
    "given_name": "Gina",
    "family_name": "Google",
}


def test_google_start_returns_authorization_url(api):
    r = api.get(f"{V1}/auth/social/google/")
    url = r.json()["data"]["authorization_url"]
    assert r.status_code == 200 and url.startswith("https://accounts.google.com/") and "test-google-client-id" in url
    redirect = api.get(f"{V1}/auth/social/google/", {"redirect": "1"})
    assert redirect.status_code == 302


def test_google_start_not_configured(api, settings):
    settings.GOOGLE_CLIENT_ID = ""
    assert api.get(f"{V1}/auth/social/google/").status_code == 503


def test_google_sign_in_creates_verified_account_and_tokens(api):
    state = api.get(f"{V1}/auth/social/google/").json()["data"]["state"]
    p1, p2 = fake_google(CLAIMS)
    with p1, p2:
        r = api.post(f"{V1}/auth/social/google/callback/", {"code": "abc", "state": state}, format="json")
    body = assert_envelope(r, True)
    assert r.status_code == 200 and body["data"]["user"]["email"] == "gina@example.test"
    assert body["data"]["user"]["email_verified"] is True
    user = User.objects.get(email="gina@example.test")
    assert not user.has_usable_password() and user.first_name == "Gina"
    # second sign-in re-uses the same account
    p1, p2 = fake_google(CLAIMS)
    with p1, p2:
        api.post(f"{V1}/auth/social/google/callback/", {"id_token": "tok"}, format="json")
    assert User.objects.filter(email="gina@example.test").count() == 1


def test_google_links_existing_account_by_email(api, user):
    p1, p2 = fake_google({**CLAIMS, "email": user.email})
    with p1, p2:
        r = api.post(f"{V1}/auth/social/google/callback/", {"id_token": "tok"}, format="json")
    assert r.status_code == 200 and r.json()["data"]["user"]["uuid"] == str(user.uuid)


def test_google_rejects_wrong_audience_unverified_email_and_bad_state(api):
    for claims in ({**CLAIMS, "aud": "other"}, {**CLAIMS, "email_verified": "false"}):
        p1, p2 = fake_google(claims)
        with p1, p2:
            r = api.post(f"{V1}/auth/social/google/callback/", {"id_token": "tok"}, format="json")
        assert r.status_code == 400
    bad_state = api.post(f"{V1}/auth/social/google/callback/", {"code": "abc", "state": "forged"}, format="json")
    assert bad_state.status_code == 400
    assert api.post(f"{V1}/auth/social/google/callback/", {}, format="json").status_code == 400


def test_google_browser_callback_redirects_with_tokens_in_fragment(api):
    state = api.get(f"{V1}/auth/social/google/").json()["data"]["state"]
    p1, p2 = fake_google(CLAIMS)
    with p1, p2:
        r = api.get(f"{V1}/auth/social/google/callback/", {"code": "abc", "state": state})
    assert r.status_code == 302 and "/account/#access=" in r["Location"]
    assert api.get(f"{V1}/auth/social/google/callback/").status_code == 302  # missing code -> error redirect


def test_google_deleted_account_cannot_sign_in(api):
    gone = UserFactory(email="gina@example.test")
    gone.soft_delete()
    p1, p2 = fake_google(CLAIMS)
    with p1, p2:
        r = api.post(f"{V1}/auth/social/google/callback/", {"id_token": "tok"}, format="json")
    assert r.status_code == 400
    assert EmailAddress.objects.filter(user=gone, verified=True).exists()
