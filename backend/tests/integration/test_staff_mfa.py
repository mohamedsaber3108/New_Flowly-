"""FL-09: two-step verification, lockout and admin session limits on every sign-in entrance.

Entrances: (1) Django admin login page, (2) API login /api/v1/auth/login/ (used by /team and the account portal),
(3) the account portal page itself (its script sends the code to entrance 2), (4) Google sign-in.
"""

import base64
import logging
import time
from pathlib import Path
from unittest import mock

import pytest
from allauth.account.models import EmailAddress
from django.contrib import admin as django_admin
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from django.test import RequestFactory as DjangoRequestFactory
from rest_framework.test import APIClient

from apps.accounts.admin import UserAdmin
from apps.accounts.models import User
from apps.security import lockout, service
from apps.security.apps import check_mfa_settings
from apps.security.middleware import LAST_SEEN, STARTED
from apps.security.models import MfaDevice, RecoveryCode
from tests.factories import PASSWORD, OwnerFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db
V1 = "/api/v1"
ADMIN_LOGIN = "/admin/login/"


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()  # lockout counters live in the cache; user ids repeat between tests


@pytest.fixture
def require(settings):
    settings.REQUIRE_STAFF_MFA = True


def enrol(user):
    """Give `user` a confirmed device. Returns (secret, recovery_codes)."""
    secret, _ = service.start_enrollment(user)
    codes = service.confirm_enrollment(user, service.totp_now(secret))
    assert codes and len(codes) == 10
    return secret, codes


def fresh_code(user):
    """A valid current code, even right after another one was used (clears the replay guard for the test)."""
    MfaDevice.objects.filter(user=user).update(last_step=0)
    return service.totp_now(service.decrypt_secret(user.mfa_device.secret))


def api_login(email, password=PASSWORD, code=None):
    body = {"email": email, "password": password}
    if code is not None:
        body["code"] = code
    return APIClient().post(f"{V1}/auth/login/", body, format="json")


def admin_login(client, email, password=PASSWORD, otp=""):
    return client.post(ADMIN_LOGIN, {"username": email, "password": password, "otp": otp})


def signed_in(client):
    return "_auth_user_id" in client.session


# --- the TOTP code itself --------------------------------------------------------------------------------------------


def test_totp_matches_the_rfc_6238_test_vectors():
    secret = base64.b32encode(b"12345678901234567890").decode()  # the RFC's SHA-1 test key
    # RFC 6238 appendix B lists 8 digits (94287082, 07081804, 89005924); we use the last 6 digits.
    assert service.totp_now(secret, now=59) == "287082"
    assert service.totp_now(secret, now=1111111109) == "081804"
    assert service.totp_now(secret, now=1234567890) == "005924"


def test_a_code_works_once_and_old_or_far_codes_do_not():
    user = StaffFactory()
    secret, _ = enrol(user)
    now = time.time()
    far = service.totp_now(secret, now=now + 600)
    assert service.verify_second_factor(user, far) is False
    code = service.totp_now(secret, now=now + 30)  # next step: inside the drift window, newer than the enrolment code
    assert service.verify_second_factor(user, code) is True
    assert service.verify_second_factor(user, code) is False  # replay


# --- recovery codes ----------------------------------------------------------------------


def test_recovery_code_works_once_and_ignores_case_and_dashes():
    user = StaffFactory()
    _, codes = enrol(user)
    first = codes[0]
    assert service.verify_second_factor(user, first.upper().replace("-", " ")) is True
    assert service.verify_second_factor(user, first) is False  # already used
    assert service.verify_second_factor(user, codes[1]) is True
    assert RecoveryCode.objects.filter(user=user, used_at__isnull=False).count() == 2
    assert service.verify_second_factor(user, "aaaaa-bbbbb") is False


# --- entrance 1: Django admin ----------------------------------------------------------------------------------------


def test_admin_login_without_a_second_factor_is_refused_when_required(require):
    staff = StaffFactory()  # no device
    client = Client()
    response = admin_login(client, staff.email)
    assert response.status_code == 200 and not signed_in(client)
    assert b"Two-step verification is required" in response.content


def test_admin_login_with_a_device_needs_the_right_code(require):
    staff = StaffFactory()
    _, codes = enrol(staff)
    client = Client()
    assert not signed_in(client)
    for otp, expected in (("", b"Enter the verification code"), ("000000", b"not valid")):
        response = admin_login(client, staff.email, otp=otp)
        assert response.status_code == 200 and not signed_in(client) and expected in response.content
    ok = admin_login(client, staff.email, otp=fresh_code(staff))
    assert ok.status_code == 302 and signed_in(client)


def test_admin_login_accepts_a_recovery_code_once(require):
    staff = StaffFactory()
    _, codes = enrol(staff)
    first = Client()
    assert admin_login(first, staff.email, otp=codes[0]).status_code == 302 and signed_in(first)
    second = Client()
    assert admin_login(second, staff.email, otp=codes[0]).status_code == 200 and not signed_in(second)


def test_admin_login_still_works_without_the_rule_for_people_who_never_enrolled():
    staff = StaffFactory()  # REQUIRE_STAFF_MFA is off (default)
    client = Client()
    assert admin_login(client, staff.email).status_code == 302 and signed_in(client)


def test_admin_login_asks_enrolled_staff_for_a_code_even_while_the_rule_is_off():
    staff = StaffFactory()
    enrol(staff)
    client = Client()
    assert admin_login(client, staff.email).status_code == 200 and not signed_in(client)


# --- entrance 2: API login (/team console and the account portal) -----------------------------------------------------


def test_api_login_without_a_device_is_refused_with_a_clear_code_and_no_tokens(require):
    staff = StaffFactory()
    response = api_login(staff.email)
    assert response.status_code == 403
    body = response.json()
    assert body["errors"]["code"] == "mfa_enrollment_required" and "access" not in str(body)


def test_api_login_with_a_device_needs_the_code_and_then_issues_tokens(require):
    staff = StaffFactory()
    enrol(staff)
    missing = api_login(staff.email)
    assert missing.status_code == 403 and missing.json()["errors"]["code"] == "mfa_required"
    wrong = api_login(staff.email, code="123456")
    assert wrong.status_code == 401 and wrong.json()["errors"]["code"] == "mfa_invalid"
    ok = api_login(staff.email, code=fresh_code(staff))
    assert ok.status_code == 200 and ok.json()["data"]["access"] and ok.json()["data"]["user"]["email"] == staff.email


def test_api_login_recovery_code_works_once(require):
    staff = StaffFactory()
    _, codes = enrol(staff)
    assert api_login(staff.email, code=codes[3]).status_code == 200
    assert api_login(staff.email, code=codes[3]).status_code == 401


def test_owner_and_superuser_also_need_the_second_factor(require):
    owner = OwnerFactory()
    root = User.objects.create_superuser(email="root@example.test", password=PASSWORD)
    EmailAddress.objects.create(user=root, email=root.email, primary=True, verified=True)
    assert api_login(owner.email).json()["errors"]["code"] == "mfa_enrollment_required"
    assert api_login(root.email).json()["errors"]["code"] == "mfa_enrollment_required"


def test_customers_never_need_a_code(require):
    customer = UserFactory()
    assert api_login(customer.email).status_code == 200


def test_the_account_portal_page_and_script_carry_the_code_field():
    """Entrance 3. The portal page loads portal.js, whose sign-in form posts to the API login (entrance 2) with the
    code field, so the API tests above apply to it."""
    portal = Client().get("/account/")
    assert portal.status_code == 200 and b"portal.js" in portal.content
    script = (Path(__file__).resolve().parents[2] / "static" / "account" / "portal.js").read_text()
    assert "field('code', 'Verification code (staff accounts only)'" in script
    assert "api('/auth/login/', { method: 'POST', body: d, anon: true })" in script


# --- entrance 4: Google sign-in ---------------------------------------------------------------------------------------


def test_google_sign_in_is_refused_for_team_accounts_that_need_a_second_factor(require):
    staff = StaffFactory()
    enrol(staff)
    with mock.patch("apps.accounts.services.google_sign_in", return_value=staff):
        response = APIClient().post(f"{V1}/auth/social/google/callback/", {"id_token": "x"}, format="json")
    assert response.status_code == 403 and response.json()["errors"]["code"] == "mfa_use_password"
    assert "access" not in response.content.decode()


def test_google_sign_in_still_works_for_customers(require):
    customer = UserFactory()
    with mock.patch("apps.accounts.services.google_sign_in", return_value=customer):
        response = APIClient().post(f"{V1}/auth/social/google/callback/", {"id_token": "x"}, format="json")
    assert response.status_code == 200 and response.json()["data"]["access"]


# --- lockout: 5 failures in 15 minutes lock 15 minutes, on every entrance, counted together ---------------------------


def test_api_login_locks_after_five_wrong_passwords():
    user = UserFactory()
    for _ in range(5):
        assert api_login(user.email, password="Wrong-Password-1!").status_code == 401
    locked = api_login(user.email)  # the right password is refused too
    assert locked.status_code == 429 and locked.json()["errors"]["code"] == "locked"
    cache.clear()  # the 15 minutes pass
    assert api_login(user.email).status_code == 200


def test_admin_login_locks_after_five_wrong_passwords():
    staff = StaffFactory()
    client = Client()
    for _ in range(5):
        assert admin_login(client, staff.email, password="Wrong-Password-1!").status_code == 200
    locked = admin_login(client, staff.email)
    assert locked.status_code == 200 and not signed_in(client) and b"Too many failed sign-in attempts" in locked.content


def test_failures_on_different_entrances_count_together():
    staff = StaffFactory()
    for _ in range(3):
        api_login(staff.email, password="Wrong-Password-1!")
    client = Client()
    for _ in range(2):
        admin_login(client, staff.email, password="Wrong-Password-1!")
    assert lockout.is_locked(staff.email)
    assert api_login(staff.email).status_code == 429
    assert admin_login(client, staff.email).status_code == 200 and not signed_in(client)


def test_wrong_codes_count_towards_the_lockout(require):
    staff = StaffFactory()
    enrol(staff)
    for _ in range(5):
        api_login(staff.email, code="000000")
    right = api_login(staff.email, code=fresh_code(staff))
    assert right.status_code == 429


def test_lockout_also_blocks_google_sign_in_for_a_locked_account():
    user = UserFactory()
    for _ in range(5):
        api_login(user.email, password="Wrong-Password-1!")
    with mock.patch("apps.accounts.services.google_sign_in", return_value=user):
        response = APIClient().post(f"{V1}/auth/social/google/callback/", {"id_token": "x"}, format="json")
    assert response.status_code == 429


def test_a_successful_sign_in_resets_the_failure_count():
    user = UserFactory()
    for _ in range(4):
        api_login(user.email, password="Wrong-Password-1!")
    assert api_login(user.email).status_code == 200
    for _ in range(4):
        api_login(user.email, password="Wrong-Password-1!")
    assert api_login(user.email).status_code == 200  # 4 + 4 failures, never 5 in a row


# --- enrolment ----------------------------------------------------------------------


def post_json(path, body):
    return APIClient().post(f"{V1}/auth/mfa/{path}/", body, format="json")


def test_enrolment_api_gives_a_secret_then_ten_recovery_codes_and_cannot_be_replaced():
    staff = StaffFactory()
    start = post_json("enroll", {"email": staff.email, "password": PASSWORD})
    assert start.status_code == 200 and start.headers.get("Cache-Control", "") != "public"
    secret = start.json()["data"]["secret"]
    assert (
        start.json()["data"]["otpauth_uri"].startswith("otpauth://totp/")
        and secret in start.json()["data"]["otpauth_uri"]
    )

    bad = post_json("confirm", {"email": staff.email, "password": PASSWORD, "code": "000000"})
    assert bad.status_code == 400 and not service.has_confirmed_device(staff)
    done = post_json("confirm", {"email": staff.email, "password": PASSWORD, "code": service.totp_now(secret)})
    codes = done.json()["data"]["recovery_codes"]
    assert done.status_code == 200 and len(codes) == 10 and len(set(codes)) == 10
    assert service.has_confirmed_device(staff)

    again = post_json("enroll", {"email": staff.email, "password": PASSWORD})
    assert again.status_code == 409  # a password alone cannot swap a confirmed second factor
    assert service.decrypt_secret(MfaDevice.objects.get(user=staff).secret) == secret


def test_enrolment_needs_the_password_and_a_team_account():
    staff, customer = StaffFactory(), UserFactory()
    assert post_json("enroll", {"email": staff.email, "password": "nope"}).status_code == 401
    assert post_json("enroll", {"email": customer.email, "password": PASSWORD}).status_code == 403
    assert not MfaDevice.objects.exists()


def test_wrong_passwords_on_the_enrolment_door_count_towards_the_lockout():
    staff = StaffFactory()
    for _ in range(5):
        assert post_json("enroll", {"email": staff.email, "password": "nope"}).status_code == 401
    assert post_json("enroll", {"email": staff.email, "password": PASSWORD}).status_code == 429


def test_enrolment_page_walks_through_secret_code_and_recovery_codes():
    staff = StaffFactory()
    client = Client()
    assert client.get("/account/mfa/enroll/").status_code == 200
    step1 = client.post("/account/mfa/enroll/", {"step": "credentials", "email": staff.email, "password": PASSWORD})
    assert step1.status_code == 200 and step1["Cache-Control"] == "no-store"
    secret = service.decrypt_secret(MfaDevice.objects.get(user=staff).secret)
    assert secret in step1.content.decode()
    wrong = client.post("/account/mfa/enroll/", {"step": "confirm", "code": "000000"})
    assert wrong.status_code == 400 and not service.has_confirmed_device(staff)
    done = client.post("/account/mfa/enroll/", {"step": "confirm", "code": service.totp_now(secret)})
    assert done.status_code == 200 and service.has_confirmed_device(staff)
    assert done.content.decode().count("-") >= 10  # ten recovery codes like abcde-fghjk


def test_enrolment_says_so_when_the_server_has_no_encryption_key(settings):
    settings.MFA_ENCRYPTION_KEY = ""
    staff = StaffFactory()
    response = post_json("enroll", {"email": staff.email, "password": PASSWORD})
    assert response.status_code == 503 and "not configured" in response.json()["message"]


def test_the_system_check_stops_a_server_that_requires_mfa_without_a_key(settings):
    settings.REQUIRE_STAFF_MFA = True
    settings.MFA_ENCRYPTION_KEY = ""
    assert [e.id for e in check_mfa_settings(None)] == ["security.E001"]
    settings.MFA_ENCRYPTION_KEY = "x"
    assert check_mfa_settings(None) == []


def test_an_owner_can_reset_a_lost_device_but_staff_cannot():
    owner, staff, other = OwnerFactory(), StaffFactory(), StaffFactory()
    enrol(staff)
    model_admin = UserAdmin(User, django_admin.site)

    def run(actor):
        request = DjangoRequestFactory().post("/admin/accounts/user/")
        request.user = actor
        request.session = {}
        request._messages = mock.MagicMock()
        model_admin.reset_two_step_verification(request, User.objects.filter(pk=staff.pk))

    run(other)  # a normal staff member
    assert service.has_confirmed_device(staff)
    run(owner)
    assert not MfaDevice.objects.filter(user=staff).exists() and not RecoveryCode.objects.filter(user=staff).exists()
    assert service.start_enrollment(staff)  # can enrol again


# --- secrets are not leaked ----------------------------------------------------------------------


def test_the_secret_is_encrypted_in_the_database_and_never_logged_or_returned_by_sign_in(caplog, require):
    caplog.set_level(logging.DEBUG)
    staff = StaffFactory()
    secret, codes = enrol(staff)
    assert secret not in MfaDevice.objects.get(user=staff).secret  # stored as a Fernet token
    login = api_login(staff.email, code=fresh_code(staff))
    assert secret not in login.content.decode() and not any(c in login.content.decode() for c in codes)
    admin_login(Client(), staff.email, otp="000000")
    log_text = caplog.text
    assert secret not in log_text and not any(c in log_text for c in codes) and PASSWORD not in log_text
    stored = list(MfaDevice.objects.values_list("secret", flat=True)) + list(
        RecoveryCode.objects.values_list("digest", flat=True)
    )
    assert not any(c in " ".join(stored) for c in codes)


# --- admin session limits ----------------------------------------------------------------------


def staff_client():
    staff = StaffFactory()
    client = Client()
    client.force_login(staff)
    assert client.get("/admin/").status_code == 200  # stamps the session
    return client


def set_session(client, **values):
    session = client.session
    session.update(values)
    session.save()


def test_staff_admin_session_ends_after_30_minutes_idle():
    client = staff_client()
    set_session(client, **{LAST_SEEN: int(time.time()) - 1801})
    response = client.get("/admin/")
    assert response.status_code == 302 and "login" in response["Location"] and "expired=1" in response["Location"]
    assert not signed_in(client)


def test_staff_admin_session_ends_after_8_hours_even_when_active():
    client = staff_client()
    set_session(client, **{STARTED: int(time.time()) - 8 * 3600 - 5, LAST_SEEN: int(time.time())})
    response = client.get("/admin/")
    assert response.status_code == 302 and "expired=1" in response["Location"] and not signed_in(client)


def test_staff_admin_session_inside_the_limits_keeps_working_and_customers_are_untouched(settings):
    client = staff_client()
    set_session(client, **{LAST_SEEN: int(time.time()) - 1700})
    assert client.get("/admin/").status_code == 200
    customer_client = Client()
    customer_client.force_login(UserFactory())
    session = customer_client.session
    session[LAST_SEEN] = 1  # an ancient value: not a staff user, so the middleware ignores it
    session.save()
    assert customer_client.get("/account/").status_code == 200 and signed_in(customer_client)
    assert AnonymousUser().is_authenticated is False


def test_the_admin_login_page_says_why_the_session_ended():
    response = Client().get(ADMIN_LOGIN + "?expired=1")
    assert response.status_code == 200 and b"Your session ended" in response.content
    assert b'name="otp"' in response.content  # the code field is on the page


def test_a_secret_that_cannot_be_decrypted_is_a_configuration_error_not_a_pass():
    with pytest.raises(ImproperlyConfigured):
        service.decrypt_secret("not-a-token")
