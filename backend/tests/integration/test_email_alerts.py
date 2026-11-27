"""FL-16 slice 1: team alert without personal data, RTL Arabic receipt, mail failures, send_test_email, mail mode."""

import json
import logging
from io import StringIO
from smtplib import SMTPException
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.utils import mail_mode, mask_address, mask_addresses_in
from apps.leads import services
from tests.factories import RequestFactory

pytestmark = pytest.mark.django_db

VISITOR = {
    "name": "Zainab Hassan",
    "email": "zainab.hassan@example.test",
    "organization": "Hassan Textiles",
}
REQUIREMENT = "We need the invoices of Hassan Textiles connected to the warehouse system."
PHONE = "+20 100 123 4567"


def make_request(**extra):
    return RequestFactory(**VISITOR, details={"requirements": REQUIREMENT, "phone": PHONE}, **extra)


def split_outbox(visitor_email):
    receipt = next(m for m in mail.outbox if visitor_email in m.to)
    alert = next(m for m in mail.outbox if visitor_email not in m.to)
    return receipt, alert


def everything(message):
    html = message.alternatives[0][0]
    return " ".join([message.subject, message.body, html])


def test_team_alert_has_the_facts_and_links_but_none_of_the_visitors_personal_data(settings):
    settings.TEAM_NOTIFY_EMAIL = "team@example.test"
    req = make_request(kind="consultation", audience="business")
    services.notify_new_request(req, None)
    _, alert = split_outbox(VISITOR["email"])
    text = everything(alert)

    assert alert.to == ["team@example.test"]
    assert req.reference in alert.subject and "طلب جديد" in alert.subject  # bilingual subject
    assert alert.body.strip() and alert.alternatives  # a text part and an HTML part
    assert req.get_kind_display() in alert.body and req.get_audience_display() in alert.body
    assert "(Cairo time)" in alert.body
    assert f"/{settings.ADMIN_URL}leads/request/{req.pk}/change/" in alert.body  # the admin change page
    assert f"{settings.FRONTEND_URL}/team" in alert.body

    for private in (VISITOR["name"], "Zainab", VISITOR["email"], VISITOR["organization"], "Hassan", REQUIREMENT, PHONE):
        assert private not in text, private
    assert "invoices" not in text and "example.test" not in text.replace("team@example.test", "")


def test_team_alert_shows_the_creation_time_in_cairo(settings):
    settings.TEAM_NOTIFY_EMAIL = "team@example.test"
    req = make_request()
    services.notify_new_request(req, None)
    _, alert = split_outbox(VISITOR["email"])
    expected = req.created_at.astimezone(ZoneInfo("Africa/Cairo")).strftime("%Y-%m-%d %H:%M")
    assert f"Created: {expected} (Cairo time)" in alert.body


def test_no_alert_is_sent_when_no_team_address_is_set(settings):
    settings.TEAM_NOTIFY_EMAIL = ""
    services.notify_new_request(make_request(), None)
    assert len(mail.outbox) == 1  # the visitor receipt only


def test_arabic_receipt_is_right_to_left_with_a_text_part(settings):
    req = make_request(language="ar")
    services.notify_new_request(req, None)
    receipt = mail.outbox[0]
    html = receipt.alternatives[0][0]
    assert '<html lang="ar" dir="rtl">' in html
    assert req.reference in receipt.body and VISITOR["name"] in receipt.body  # text-only part is complete
    assert "<" not in receipt.body  # really plain text
    assert f"{settings.FRONTEND_URL}/status" in receipt.body  # the status link survives in the text-only part
    assert "وصلتك هذه الرسالة" in html  # the footer is Arabic too


def test_english_receipt_stays_left_to_right_with_the_same_content():
    req = make_request(language="en")
    services.notify_new_request(req, None)
    html = mail.outbox[0].alternatives[0][0]
    assert '<html lang="en">' in html and 'dir="rtl"' not in html.split("<body", 1)[0]
    assert req.reference in mail.outbox[0].body and "We received your request" in html


def test_a_mail_failure_never_breaks_the_request_and_logs_one_masked_line_per_email(api, payload, settings, caplog):
    settings.TEAM_NOTIFY_EMAIL = "team.lead@example.test"
    caplog.set_level(logging.WARNING, logger="flowly.mail")
    refused = SMTPException("550 5.1.1 <qa@example.test>: recipient rejected; also team.lead@example.test")
    with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=refused):
        response = api.post("/api/requests", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 201 and response.json()["reference"]

    lines = [r.getMessage() for r in caplog.records if r.name == "flowly.mail"]
    assert len(lines) == 2  # the receipt and the team alert each failed once
    events = [json.loads(line.split("mail_failed ", 1)[1]) for line in lines]
    assert {e["template"] for e in events} == {"emails/request_received.html", "emails/team_alert.html"}
    assert all(e["error"] == "SMTPException" for e in events)
    assert {tuple(e["recipients"]) for e in events} == {("q***@example.test",), ("t***@example.test",)}
    assert "qa@example.test" not in caplog.text and "team.lead" not in caplog.text and "rejected" not in caplog.text


def test_masking_helpers_never_return_a_full_address():
    assert mask_address("zainab@example.test") == "z***@example.test"
    assert mask_address("not an email") == "[not an email]" and mask_address("") == "[not an email]"
    assert mask_addresses_in("550 <a.b@c.test> and d@e.test") == "550 <a***@c.test> and d***@e.test"


# --- send_test_email -------------------------------------------------------------------------------------------------


def test_send_test_email_reports_ok_for_a_real_mail_server_and_masks_the_address(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    out = StringIO()
    with mock.patch("django.core.mail.EmailMultiAlternatives.send", return_value=1) as send:
        call_command("send_test_email", "--to", "owner.person@example.test", stdout=out)
    text = out.getvalue()
    assert "Mail mode: configured" in text and "OK:" in text and "not sent" not in text
    assert "o***@example.test" in text and "owner.person" not in text
    assert send.call_count == 1


def test_send_test_email_in_console_mode_does_not_say_ok(settings):
    """The console and in-memory backends accept a message without sending it: that must not read as success."""
    for backend in ("django.core.mail.backends.console.EmailBackend", "django.core.mail.backends.locmem.EmailBackend"):
        settings.EMAIL_BACKEND = backend
        out = StringIO()
        call_command("send_test_email", "--to", "owner.person@example.test", stdout=out)
        text = out.getvalue()
        assert "Mail mode: console" in text and "console backend: not sent, check the log" in text
        assert "OK:" not in text and "owner.person" not in text


def test_production_settings_give_up_on_a_silent_mail_server_after_10_seconds():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "config" / "settings" / "production.py").read_text()
    assert 'EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)' in source


def test_send_test_email_fails_loudly_without_printing_addresses_or_secrets(settings):
    settings.EMAIL_HOST_PASSWORD = "smtp-password-should-never-print"
    error = SMTPException("535 authentication failed for owner.person@example.test")
    with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=error):
        with pytest.raises(CommandError) as info:
            call_command("send_test_email", "--to", "owner.person@example.test")
    message = str(info.value)
    assert message.startswith("FAILED: SMTPException") and "owner.person" not in message
    assert "smtp-password-should-never-print" not in message


def test_send_test_email_refuses_something_that_is_not_an_address():
    with pytest.raises(CommandError):
        call_command("send_test_email", "--to", "not-an-address")


# --- health ----------------------------------------------------------------------------------------------------------


def test_health_shows_only_the_mail_mode(api, settings):
    settings.EMAIL_HOST_USER = "smtp-user-should-not-show"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    body = api.get("/health/").json()
    assert body["data"]["mail"] == "console" and mail_mode() == "console"
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    response = api.get("/health/")
    assert response.json()["data"]["mail"] == "configured"
    assert "smtp-user-should-not-show" not in response.content.decode()
