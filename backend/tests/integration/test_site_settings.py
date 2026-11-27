"""FL-21: site settings (booking days and times, blocked days, switches), their admin pages and the module registry.

The defaults must reproduce the behaviour from before the settings existed: Sunday to Thursday, five time slots,
90 days ahead, nothing blocked, everything on.
"""

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from apps.core import modules
from apps.leads import site_settings
from apps.leads.models import BlockedDay, Request, SiteSettings
from tests.conftest import future_workday
from tests.factories import RequestFactory, StaffFactory, UserFactory

pytestmark = pytest.mark.django_db
ORIGIN = "https://flowly.test"


def cairo_today():
    return datetime.now(ZoneInfo("Africa/Cairo")).date()


def day_with_weekday(weekday, start=3):
    """The first date from `start` days ahead whose Python weekday is `weekday` (Monday=0 ... Sunday=6)."""
    day = cairo_today() + timedelta(days=start)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


def old_rule(value):
    """The rule that was hard-coded before FL-21 (serializers.valid_future_date)."""
    today = cairo_today()
    return today < value <= today + timedelta(days=90) and value.weekday() not in (4, 5)


def post_request(api, payload, path="/api/requests"):
    return api.post(path, data=json.dumps(payload), content_type="application/json")


def availability(api, date):
    return api.get("/api/availability", {"date": date})


# --- defaults are today's behaviour ------------------------------------------------------------------------------


def test_defaults_equal_the_old_hard_coded_behaviour():
    s = site_settings.get()
    assert s.weekdays == (0, 1, 2, 3, 6)  # Sunday to Thursday
    assert s.slot_times == ("10:00", "11:00", "12:00", "14:00", "15:00")
    assert s.horizon_days == 90 and s.blocked == frozenset()
    assert s.assistant_enabled is True and s.intake_enabled is True
    assert not SiteSettings.objects.exists()  # nothing had to be created for the defaults to apply


def test_every_date_from_the_past_to_past_the_horizon_is_judged_like_the_old_rule():
    from apps.leads.serializers import valid_future_date

    for offset in range(-5, 130):
        day = cairo_today() + timedelta(days=offset)
        assert valid_future_date(day.isoformat()) is old_rule(day), day
    assert not valid_future_date("2026-02-30") and not valid_future_date("garbage") and not valid_future_date("")


def test_default_availability_lists_the_five_slots_in_cairo_time_with_a_text_label(api):
    day = future_workday()
    body = availability(api, day).json()
    assert body["timezone"] == "Africa/Cairo" and body["busy"] == [] and body["closed"] is False
    assert [s["time"] for s in body["slots"]] == ["10:00", "11:00", "12:00", "14:00", "15:00"]
    assert all(s["available"] is True and "Africa/Cairo" in s["label"] for s in body["slots"])


def test_a_taken_slot_is_marked_unavailable_in_the_slot_list_and_still_in_busy(api, payload):
    assert post_request(api, payload).status_code == 201
    body = availability(api, payload["date"]).json()
    taken = [s for s in body["slots"] if s["time"] == payload["time"]][0]
    assert taken["available"] is False and payload["time"] in body["busy"]
    assert [s["available"] for s in body["slots"]].count(True) == 4


def test_default_weekend_is_still_refused_and_the_default_times_still_work(api, payload):
    friday = day_with_weekday(4)
    assert availability(api, friday.isoformat()).status_code == 400
    assert post_request(api, {**payload, "date": friday.isoformat()}).status_code == 400
    bad_time = post_request(api, {**payload, "time": "09:00"})
    assert bad_time.status_code == 400 and "not a valid choice" in bad_time.json()["error"]
    assert post_request(api, payload).status_code == 201


# --- blocked days ---------------------------------------------------------------------------------------------------


def test_a_blocked_day_disappears_from_booking_at_once_and_other_days_stay(api, payload):
    blocked, other = payload["date"], future_workday(days=11)
    assert availability(api, blocked).json()["slots"]  # open first (this also fills the cache)
    BlockedDay.objects.create(date=blocked, reason="Eid holiday")

    body = availability(api, blocked).json()
    assert body["closed"] is True and body["slots"] == [] and body["busy"] == []
    assert "Eid" not in json.dumps(body)  # the reason is for the team only
    refused = post_request(api, payload)
    assert refused.status_code == 400 and "working day" in refused.json()["error"]
    assert not Request.objects.exists()
    assert availability(api, other).json()["closed"] is False
    assert (
        post_request(api, {**payload, "date": other, "requestKey": "6f1c2f1e-5a3b-4c8e-9d7a-1b2c3d4e5f60"}).status_code
        == 201
    )

    BlockedDay.objects.filter(date=blocked).delete()  # unblock: open again at once
    assert availability(api, blocked).json()["closed"] is False


def test_the_v1_endpoints_follow_the_same_settings(api, payload):
    BlockedDay.objects.create(date=payload["date"])
    body = api.get("/api/v1/availability/", {"date": payload["date"]}).json()["data"]
    assert body["closed"] is True and body["slots"] == []


# --- weekdays, slot times, horizon ---------------------------------------------------------------------------------


def test_changing_the_booking_weekdays_changes_what_is_offered_and_accepted(api, payload):
    friday, sunday = day_with_weekday(4), day_with_weekday(6)
    SiteSettings.objects.create(booking_weekdays=[4])  # Friday only
    assert availability(api, friday.isoformat()).status_code == 200
    assert availability(api, sunday.isoformat()).status_code == 400
    assert post_request(api, {**payload, "date": sunday.isoformat()}).status_code == 400
    assert post_request(api, {**payload, "date": friday.isoformat()}).status_code == 201


def test_changing_the_slot_times_changes_the_list_and_the_accepted_times(api, payload):
    SiteSettings.objects.create(slot_times=["09:00", "13:30"])
    body = availability(api, payload["date"]).json()
    assert [s["time"] for s in body["slots"]] == ["09:00", "13:30"]
    assert post_request(api, {**payload, "time": "10:00"}).status_code == 400  # an old slot is not offered any more
    assert post_request(api, {**payload, "time": "13:30"}).status_code == 201


def test_the_horizon_is_read_from_the_settings(api, payload):
    SiteSettings.objects.create(booking_horizon_days=10)
    near, far = future_workday(days=6), future_workday(days=20)
    assert availability(api, near).status_code == 200 and availability(api, far).status_code == 400
    refused = post_request(api, {**payload, "date": far})
    assert refused.status_code == 400 and "within 10 days" in refused.json()["error"]


def test_the_horizon_error_is_in_the_visitors_language_with_digits_to_match(api, payload):
    SiteSettings.objects.create(booking_horizon_days=10)
    far = future_workday(days=20)
    arabic = post_request(api, {**payload, "date": far, "language": "ar"}).json()["error"]
    assert "خلال ١٠ يومًا" in arabic and "within" not in arabic
    english = post_request(api, {**payload, "date": far, "language": "en"}).json()["error"]
    assert "within 10 days" in english and "خلال" not in english


def test_the_calendar_endpoint_gives_open_weekdays_horizon_and_blocked_dates_without_the_reason(api):
    default = api.get("/api/availability", {"calendar": "1"}).json()
    assert default["weekdays"] == [0, 1, 2, 3, 4]  # Sunday to Thursday, JavaScript numbering (Sunday=0)
    assert default["horizonDays"] == 90 and default["blocked"] == [] and default["timezone"] == "Africa/Cairo"
    SiteSettings.objects.create(booking_weekdays=[0, 6], booking_horizon_days=20)  # Monday and Sunday
    soon, far = cairo_today() + timedelta(days=5), cairo_today() + timedelta(days=40)
    BlockedDay.objects.create(date=soon, reason="Team away")
    BlockedDay.objects.create(date=far, reason="Outside the range")
    body = api.get("/api/availability", {"calendar": "1"}).json()
    assert body["weekdays"] == [0, 1] and body["horizonDays"] == 20
    assert body["blocked"] == [soon.isoformat()]  # only dates inside the range
    assert "Team away" not in json.dumps(body)
    assert api.get("/api/v1/availability/", {"calendar": "1"}).json()["data"]["weekdays"] == [0, 1]
    assert api.get("/api/availability").status_code == 400  # a date is still required without the calendar flag


def test_the_settings_table_refuses_bulk_create_so_it_stays_one_row():
    with pytest.raises(TypeError):
        SiteSettings.objects.bulk_create([SiteSettings(), SiteSettings()])
    assert SiteSettings.objects.count() == 0


def test_settings_are_cached_for_a_minute_and_cleared_on_save(django_assert_num_queries):
    site_settings.get()
    with django_assert_num_queries(0):
        site_settings.get()
    SiteSettings.objects.create(booking_horizon_days=30)  # a save clears the cache
    assert site_settings.get().horizon_days == 30
    BlockedDay.objects.create(date=cairo_today() + timedelta(days=5))
    assert len(site_settings.get().blocked) == 1


# --- switches ---------------------------------------------------------------------------------------------------------


def test_intake_off_refuses_new_requests_clearly_in_both_languages_and_saves_nothing(api, payload):
    RequestFactory()
    SiteSettings.objects.create(intake_enabled=False)
    for language, expected in (("en", "paused"), ("ar", "متوقف مؤقتًا")):
        legacy = post_request(api, {**payload, "language": language})
        assert legacy.status_code == 503 and expected in legacy.json()["error"]
        v1 = post_request(api, {**payload, "language": language}, path="/api/v1/requests/")
        assert v1.status_code == 503 and expected in v1.json()["message"]
    assert post_request(api, {k: v for k, v in payload.items() if k != "language"}).status_code == 503
    assert Request.objects.count() == 1  # only the one that was already there


def test_requests_received_before_intake_was_switched_off_stay_usable():
    from django.test import Client as DjangoClient

    existing = RequestFactory(email="old@example.test")
    SiteSettings.objects.create(intake_enabled=False)
    found = DjangoClient().post(
        "/api/request-status",
        data=json.dumps({"reference": existing.reference, "email": "old@example.test"}),
        content_type="application/json",
    )
    assert found.status_code == 200 and found.json()["reference"] == existing.reference
    assert Request.objects.get(pk=existing.pk).status == existing.status


def test_assistant_off_says_so_in_the_visitors_language(api):
    SiteSettings.objects.create(assistant_enabled=False)
    for language, expected in (("en", "switched off"), ("ar", "متوقف")):
        body = {"message": "I need an ERP", "language": language, "history": []}
        r = api.post("/api/assistant", data=json.dumps(body), content_type="application/json")
        assert r.status_code == 503 and expected in r.json()["error"]
    SiteSettings.objects.filter(pk=1).update(assistant_enabled=True)
    site_settings.clear_cache()
    ok = api.post(
        "/api/assistant", data=json.dumps({"message": "erp", "language": "en"}), content_type="application/json"
    )
    assert ok.status_code == 200 and ok.json()["reply"]


def test_the_settings_model_holds_no_secret_fields():
    names = {f.name for f in SiteSettings._meta.get_fields()}
    assert not [n for n in names if any(w in n for w in ("key", "secret", "token", "password", "pass"))]


# --- admin ----------------------------------------------------------------------------------------------------------

URL = "/admin/leads/sitesettings/1/change/"
FORM = {
    "assistant_enabled": "on",
    "intake_enabled": "on",
    "booking_weekdays": ["6", "0", "1", "2", "3"],
    "slot_times": "10:00, 11:00, 12:00, 14:00, 15:00",
    "booking_horizon_days": "90",
    "_save": "Save",
}


def staff_client(**user_kwargs):
    user = UserFactory(**user_kwargs) if user_kwargs else StaffFactory()
    client = Client()
    client.force_login(user)
    return client, user


def events(caplog):
    return [
        json.loads(r.getMessage().split("admin_event ", 1)[1])
        for r in caplog.records
        if r.name == "flowly.admin" and "admin_event" in r.getMessage()
    ]


def test_staff_can_open_and_change_the_settings_and_it_takes_effect(api, payload, caplog):
    caplog.set_level(logging.INFO, logger="flowly.admin")
    client, user = staff_client()
    page = client.get("/admin/leads/sitesettings/", follow=True)
    assert page.status_code == 200 and b"Consultation booking" in page.content
    assert SiteSettings.objects.filter(pk=1).exists()  # created on the first visit

    data = {**FORM, "slot_times": "14:00, 9:30x", "booking_horizon_days": "30"}
    bad = client.post(URL, data)
    assert bad.status_code == 200 and b"Use the form HH:MM" in bad.content  # nothing saved
    assert SiteSettings.objects.get(pk=1).booking_horizon_days == 90

    good = client.post(URL, {**FORM, "slot_times": "15:00, 10:00, 10:00", "booking_horizon_days": "30"})
    assert good.status_code == 302
    saved = SiteSettings.objects.get(pk=1)
    assert saved.slot_times == ["10:00", "15:00"] and saved.booking_horizon_days == 30  # sorted, no duplicates
    assert saved.updated_by == user
    assert [s["time"] for s in availability(api, payload["date"]).json()["slots"]] == ["10:00", "15:00"]

    change = [e for e in events(caplog) if e["event"] == "settings.changed"][0]
    assert change["email"] == user.email and change["changes"]["booking_horizon_days"] == [90, 30]
    assert change["changes"]["slot_times"] == [["10:00", "11:00", "12:00", "14:00", "15:00"], ["10:00", "15:00"]]


def test_the_form_refuses_no_days_and_a_horizon_out_of_range():
    client, _ = staff_client()
    client.get("/admin/leads/sitesettings/", follow=True)
    no_days = client.post(URL, {k: v for k, v in FORM.items() if k != "booking_weekdays"})
    assert no_days.status_code == 200 and b"Choose at least one day" in no_days.content
    far = client.post(URL, {**FORM, "booking_horizon_days": "400"})
    assert far.status_code == 200 and SiteSettings.objects.get(pk=1).booking_horizon_days == 90


def test_switching_a_module_off_in_the_admin_is_logged_and_works(api, payload, caplog):
    caplog.set_level(logging.INFO, logger="flowly.admin")
    client, _ = staff_client()
    client.get("/admin/leads/sitesettings/", follow=True)
    off = {k: v for k, v in FORM.items() if k != "intake_enabled"}
    assert client.post(URL, off).status_code == 302
    assert post_request(api, payload).status_code == 503
    assert [e["changes"] for e in events(caplog) if e["event"] == "settings.changed"] == [
        {"intake_enabled": [True, False]}
    ]


def test_a_viewer_can_look_but_not_change(api, payload):
    SiteSettings.objects.create()
    client, _ = staff_client(role="viewer", is_staff=True)
    page = client.get(URL)
    assert page.status_code == 200 and b'name="_save"' not in page.content  # no save button for a viewer
    changed = client.post(URL, {**FORM, "booking_horizon_days": "30"})
    assert changed.status_code == 403
    assert SiteSettings.objects.get(pk=1).booking_horizon_days == 90
    assert client.get("/admin/leads/blockedday/").status_code == 200
    assert client.get("/admin/leads/blockedday/add/").status_code == 403
    assert client.post("/admin/leads/blockedday/add/", {"date": payload["date"], "reason": "x"}).status_code == 403
    assert not BlockedDay.objects.exists()


def test_a_customer_and_a_visitor_cannot_reach_the_settings():
    customer = UserFactory()
    client = Client()
    client.force_login(customer)
    assert client.get(URL).status_code == 302  # not staff: sent to the admin sign-in
    assert Client().get(URL).status_code == 302
    assert Client().post(URL, FORM).status_code == 302


def test_staff_add_and_remove_blocked_days_with_log_lines(api, payload, caplog):
    caplog.set_level(logging.INFO, logger="flowly.admin")
    client, user = staff_client()
    added = client.post(
        "/admin/leads/blockedday/add/", {"date": payload["date"], "reason": "Team away", "_save": "Save"}
    )
    assert added.status_code == 302 and BlockedDay.objects.filter(date=payload["date"]).exists()
    assert availability(api, payload["date"]).json()["closed"] is True
    day = BlockedDay.objects.get(date=payload["date"])
    removed = client.post(f"/admin/leads/blockedday/{day.pk}/delete/", {"post": "yes"})
    assert removed.status_code == 302 and not BlockedDay.objects.exists()
    assert availability(api, payload["date"]).json()["closed"] is False
    assert [e["event"] for e in events(caplog)] == ["blocked_day.added", "blocked_day.removed"]
    assert events(caplog)[0]["email"] == user.email and events(caplog)[0]["date"] == payload["date"]


# --- module registry ------------------------------------------------------------------------------------------------


def test_the_module_registry_lists_every_module_with_health_and_switch():
    rows = {r["id"]: r for r in modules.registry(site_settings.get())}
    assert set(rows) == {"intake", "booking", "assistant", "team-console", "account-portal", "admin", "mail"}
    assert all(r["healthy"] and r["name"] and r["roles"] for r in rows.values())
    assert rows["intake"]["enabled"] and rows["assistant"]["enabled"]
    SiteSettings.objects.create(intake_enabled=False, assistant_enabled=False)
    rows = {r["id"]: r for r in modules.registry(site_settings.get())}
    assert not rows["intake"]["enabled"] and not rows["booking"]["enabled"] and not rows["assistant"]["enabled"]


def test_the_registry_page_shows_a_failing_backend_as_failed(monkeypatch):
    monkeypatch.setattr(modules, "_database", lambda: (False, "database error: OperationalError"))
    client, _ = staff_client()
    page = client.get("/admin/leads/sitesettings/", follow=True)
    html = page.content.decode()
    assert "Module registry" in html and "FAILED: database error: OperationalError" in html
    assert "OK: no external service" in html  # the assistant row has no outside dependency
    assert 'scope="col"' in html  # a real table with header cells, readable by a screen reader
