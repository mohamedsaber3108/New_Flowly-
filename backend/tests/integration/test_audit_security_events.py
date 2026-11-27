"""FL-09b and FL-21b: two-step verification, sign-in locks, token revocation and settings changes are audit entries.

Never a secret, a code or a recovery code in an entry. Where the event is sensitive the audit write is fail closed: if
it cannot be written, the change does not happen.
"""

import json
from io import StringIO
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditEntry
from apps.leads.models import BlockedDay, SiteSettings
from apps.security import lockout, service
from apps.security.models import MfaDevice, RecoveryCode
from tests.factories import OwnerFactory, StaffFactory, UserFactory
from tests.integration.test_site_settings import FORM, URL

pytestmark = pytest.mark.django_db

IP = "203.0.113.7"


def entries(action):
    return list(AuditEntry.objects.filter(action=action).order_by("id"))


def enrol(user):
    secret, _ = service.start_enrollment(user)
    codes = service.confirm_enrollment(user, service.totp_now(secret))
    return secret, codes


def everything_stored():
    """Every audit row as one text, to look for values that must never be in it."""
    return json.dumps(
        [
            [e.action, e.target_type, e.target_id, e.before, e.after, e.reason, e.actor_label]
            for e in AuditEntry.objects.all()
        ],
        default=str,
    )


def owner_client(superuser=False):
    owner = OwnerFactory(is_superuser=superuser)
    client = Client()
    client.force_login(owner)
    return client, owner


# --- two-step verification ---


def test_enrol_start_and_confirm_are_audited_without_the_secret_or_the_codes():
    staff = StaffFactory()
    secret, _ = service.start_enrollment(staff)
    (started,) = entries("mfa.enrol_started")
    assert started.actor_id == staff.pk and started.target_id == str(staff.pk) and started.target_type == "user"
    codes = service.confirm_enrollment(staff, service.totp_now(secret))
    (confirmed,) = entries("mfa.enrol_confirmed")
    assert confirmed.after == {"recovery_codes_made": 10} and confirmed.actor_label == staff.email
    stored = everything_stored()
    assert secret not in stored and not any(code in stored for code in codes)


def test_a_wrong_code_at_enrolment_writes_no_confirm_entry():
    staff = StaffFactory()
    service.start_enrollment(staff)
    assert service.confirm_enrollment(staff, "000000") is None
    assert entries("mfa.enrol_confirmed") == []


def test_enrolment_is_fail_closed_no_audit_entry_no_device():
    staff = StaffFactory()
    with mock.patch("apps.security.service.audit.record", side_effect=DatabaseError("audit table down")):
        with pytest.raises(DatabaseError):
            service.start_enrollment(staff)
    assert not MfaDevice.objects.filter(user=staff).exists()
    secret, _ = service.start_enrollment(staff)
    with mock.patch("apps.security.service.audit.record", side_effect=DatabaseError("audit table down")):
        with pytest.raises(DatabaseError):
            service.confirm_enrollment(staff, service.totp_now(secret))
    assert not MfaDevice.objects.get(user=staff).confirmed_at  # still not switched on
    assert not RecoveryCode.objects.filter(user=staff).exists()


def test_using_a_recovery_code_is_audited_once_with_the_count_left_and_never_the_code():
    staff = StaffFactory()
    _, codes = enrol(staff)
    assert service.verify_second_factor(staff, codes[0]) is True
    (used,) = entries("mfa.recovery_used")
    assert used.actor_id == staff.pk and used.after == {"recovery_codes_left": 9}
    assert service.verify_second_factor(staff, codes[0]) is False  # the same code again: refused, no new entry
    assert len(entries("mfa.recovery_used")) == 1
    assert codes[0] not in everything_stored() and codes[0].replace("-", "") not in everything_stored()


def test_an_authenticator_code_is_not_a_recovery_entry_and_a_failed_audit_keeps_the_recovery_code_unused():
    staff = StaffFactory()
    secret, codes = enrol(staff)
    MfaDevice.objects.filter(user=staff).update(last_step=0)
    assert service.verify_second_factor(staff, service.totp_now(secret)) is True
    assert entries("mfa.recovery_used") == []
    with mock.patch("apps.security.service.audit.record", side_effect=DatabaseError("audit table down")):
        with pytest.raises(DatabaseError):
            service.verify_second_factor(staff, codes[1])
    assert RecoveryCode.objects.filter(user=staff, used_at__isnull=True).count() == 10  # not used up


def test_an_owner_resetting_a_device_in_the_admin_is_audited_with_who_did_it():
    client, owner = owner_client(superuser=True)
    staff = StaffFactory()
    enrol(staff)
    response = client.post(
        "/admin/accounts/user/",
        {"action": "reset_two_step_verification", "_selected_action": [str(staff.pk)]},
    )
    assert response.status_code == 302 and not MfaDevice.objects.filter(user=staff).exists()
    (reset,) = entries("mfa.reset")
    assert reset.actor_id == owner.pk and reset.target_id == str(staff.pk)
    assert reset.after == {"by": f"{owner.email} (admin action)"}


def test_the_break_glass_command_is_audited_with_the_server_user_and_host():
    staff = StaffFactory()
    enrol(staff)
    call_command("reset_staff_mfa", "--email", staff.email, stdout=StringIO())
    (reset,) = entries("mfa.reset")
    assert reset.actor_id is None and reset.target_id == str(staff.pk)
    assert reset.after["by"] == "management command reset_staff_mfa"
    assert reset.after["os_user"] and reset.after["host"] and "sudo_user" in reset.after


def test_a_reset_is_fail_closed_if_the_audit_entry_cannot_be_written():
    staff = StaffFactory()
    enrol(staff)
    with mock.patch("apps.security.service.audit.record", side_effect=DatabaseError("audit table down")):
        with pytest.raises(DatabaseError):
            service.reset_device(staff, by="test")
    assert MfaDevice.objects.filter(user=staff).exists() and RecoveryCode.objects.filter(user=staff).exists()


# --- sign-in locks ---


def test_a_sign_in_lock_is_audited_with_a_masked_email_and_never_the_typed_text():
    for _ in range(5):
        lockout.register_failure("someone@example.test", IP)
    locked = entries("signin.locked")
    assert locked and locked[0].after["scope"] == "email+ip" and locked[0].result == "denied"
    assert locked[0].after["email"] == "s***@example.test" and locked[0].after["ip"] == IP
    assert "someone" not in everything_stored()


def test_a_password_typed_into_the_email_box_is_never_in_the_lock_entry():
    typed = "My-Secret-Passw0rd!"
    for _ in range(5):
        lockout.register_failure(typed, IP)
    locked = entries("signin.locked")
    assert locked and locked[0].after["email"] == "[not an email]"
    assert typed not in everything_stored()


def test_clearing_a_lock_in_the_admin_is_audited_and_the_lock_really_ends():
    client, owner = owner_client(superuser=True)
    staff = StaffFactory()
    for _ in range(5):
        lockout.register_failure(staff.email, IP)
    assert lockout.is_locked(staff.email, IP)
    client.post("/admin/accounts/user/", {"action": "clear_sign_in_lock", "_selected_action": [str(staff.pk)]})
    (cleared,) = entries("signin.unlocked")
    assert cleared.actor_id == owner.pk and cleared.after["email"].endswith("@example.test")
    assert not lockout.is_locked(staff.email, IP)


def test_clearing_a_lock_is_fail_closed():
    staff = StaffFactory()
    for _ in range(5):
        lockout.register_failure(staff.email, IP)
    with mock.patch("apps.security.lockout.audit.record", side_effect=DatabaseError("audit table down")):
        with pytest.raises(DatabaseError):
            lockout.clear_email(staff.email, by="test")
    assert lockout.is_locked(staff.email, IP)  # still locked: nothing was cleared without a record


def test_a_lock_still_starts_if_the_audit_entry_cannot_be_written():
    with mock.patch("apps.security.lockout.audit.record", side_effect=DatabaseError("audit table down")):
        # best effort: the audit module swallows the error for a non-sensitive entry, so the real call is patched
        # here only to prove the lock does not depend on it being a success
        for _ in range(5):
            try:
                lockout.register_failure("late@example.test", IP)
            except DatabaseError:
                pass
    assert cache.get(lockout._email_key("lock-pair", "late@example.test", IP)) == 1


# --- revoking team tokens ---


def test_revoke_staff_tokens_is_audited_with_counts_only():
    staff, customer = StaffFactory(), UserFactory()
    tokens = [
        str(RefreshToken.for_user(staff)),
        str(RefreshToken.for_user(staff)),
        str(RefreshToken.for_user(customer)),
    ]
    call_command("revoke_staff_tokens", stdout=StringIO())
    (revoked,) = entries("tokens.revoked")
    assert revoked.after["revoked"] == 2 and revoked.after["team_accounts"] == 1
    assert revoked.after["os_user"] and revoked.after["host"] and "created_before" in revoked.after
    assert not any(token in everything_stored() for token in tokens)
    call_command("revoke_staff_tokens", stdout=StringIO())  # again: nothing left to revoke, still an honest entry
    assert entries("tokens.revoked")[-1].after["revoked"] == 0


def test_revoke_staff_tokens_is_fail_closed():
    staff = StaffFactory()
    token = str(RefreshToken.for_user(staff))
    with mock.patch(
        "apps.accounts.management.commands.revoke_staff_tokens.audit.record", side_effect=DatabaseError("x")
    ):
        with pytest.raises(DatabaseError):
            call_command("revoke_staff_tokens", stdout=StringIO())
    assert RefreshToken(token)  # not blacklisted: constructing it would raise if it were


# --- settings and blocked days ---


def test_a_settings_change_is_audited_with_only_the_changed_fields():
    client, owner = owner_client()
    client.get("/admin/leads/sitesettings/", follow=True)
    assert client.post(URL, {**FORM, "booking_horizon_days": "30", "slot_times": "10:00, 15:00"}).status_code == 302
    (change,) = [e for e in entries("settings.change") if e.target_id == "site_settings"]
    assert change.actor_id == owner.pk and change.target_type == "setting"
    assert change.before == {
        "booking_horizon_days": 90,
        "slot_times": ["10:00", "11:00", "12:00", "14:00", "15:00"],
    }
    assert change.after == {"booking_horizon_days": 30, "slot_times": ["10:00", "15:00"]}


def test_saving_the_settings_page_without_a_change_writes_no_entry():
    client, _ = owner_client()
    client.get("/admin/leads/sitesettings/", follow=True)
    client.post(URL, FORM)
    assert entries("settings.change") == []


def test_a_settings_change_is_fail_closed_it_is_rolled_back_if_the_audit_entry_fails():
    client, _ = owner_client()
    client.get("/admin/leads/sitesettings/", follow=True)
    with mock.patch("apps.leads.settings_admin.audit.record_settings_change", side_effect=DatabaseError("down")):
        with pytest.raises(DatabaseError):
            client.post(URL, {**FORM, "booking_horizon_days": "30"})
    assert SiteSettings.objects.get(pk=1).booking_horizon_days == 90


def test_blocked_days_added_changed_and_removed_are_audited_with_before_and_after():
    client, owner = owner_client()
    added = client.post("/admin/leads/blockedday/add/", {"date": "2031-01-05", "reason": "Team away", "_save": "Save"})
    assert added.status_code == 302
    day = BlockedDay.objects.get()
    (first,) = [e for e in entries("settings.change") if e.target_type == "blocked_day"]
    assert first.target_id == "2031-01-05" and first.before is None
    assert first.after == {"date": "2031-01-05", "reason": "Team away"} and first.actor_id == owner.pk
    client.post(
        f"/admin/leads/blockedday/{day.pk}/change/", {"date": "2031-01-05", "reason": "Holiday", "_save": "Save"}
    )
    second = [e for e in entries("settings.change") if e.target_type == "blocked_day"][-1]
    assert second.before == {"date": "2031-01-05", "reason": "Team away"}
    assert second.after == {"date": "2031-01-05", "reason": "Holiday"}
    client.post(f"/admin/leads/blockedday/{day.pk}/delete/", {"post": "yes"})
    removed = [e for e in entries("settings.change") if e.target_type == "blocked_day"][-1]
    assert removed.before == {"date": "2031-01-05", "reason": "Holiday"} and removed.after is None
    assert not BlockedDay.objects.exists()


def test_removing_a_blocked_day_is_fail_closed():
    client, _ = owner_client()
    day = BlockedDay.objects.create(date="2031-02-01", reason="x")
    with mock.patch("apps.leads.settings_admin.audit.record", side_effect=DatabaseError("down")):
        with pytest.raises(DatabaseError):
            client.post(f"/admin/leads/blockedday/{day.pk}/delete/", {"post": "yes"})
    assert BlockedDay.objects.filter(pk=day.pk).exists()


def test_the_existing_log_lines_are_kept_next_to_the_audit_entries(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="flowly.admin")
    client, _ = owner_client()
    client.get("/admin/leads/sitesettings/", follow=True)
    client.post(URL, {**FORM, "booking_horizon_days": "30"})
    assert any("settings.changed" in r.getMessage() for r in caplog.records if r.name == "flowly.admin")
    assert len(entries("settings.change")) == 1
