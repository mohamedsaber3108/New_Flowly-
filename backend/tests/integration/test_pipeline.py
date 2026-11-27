"""FL-15: lead pipeline (source, follow-up date, quote status, value range, first reply) in the admin.

The customer must never see any of the new fields; every team change is audited.
"""

import importlib
import json
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.contrib import admin as django_admin
from django.db import migrations
from django.test import Client
from django.test import RequestFactory as DjangoRequestFactory
from django.utils import timezone

from apps.audit.models import AuditEntry
from apps.leads import pipeline, services
from apps.leads.admin import RequestAdmin
from apps.leads.models import Request, RequestEvent
from apps.leads.serializers import MyRequestDetailSerializer
from tests.factories import OwnerFactory, RequestFactory, UserFactory

pytestmark = pytest.mark.django_db

PRIVATE = {
    "quote_status",
    "value_range",
    "next_follow_up",
    "first_reply_at",
    "source_page",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "internal_note",
}


def post_request(api, payload):
    return api.post("/api/requests", data=json.dumps(payload), content_type="application/json")


# --- migration -------------------------------------------------------------------------------------------------------


def test_the_leads_migration_only_adds_columns_that_old_rows_can_have():
    migration = importlib.import_module("apps.leads.migrations.0002_request_pipeline")
    assert migration.Migration.operations and all(
        isinstance(op, migrations.AddField) for op in migration.Migration.operations
    )
    for op in migration.Migration.operations:  # each new column is nullable or has a default: old rows stay valid
        assert op.field.null or op.field.has_default(), op.name
    assert {op.name for op in migration.Migration.operations} == {
        "source_page",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "next_follow_up",
        "quote_status",
        "value_range",
        "first_reply_at",
    }


def test_the_audit_migration_only_changes_the_list_of_actions():
    migration = importlib.import_module("apps.audit.migrations.0002_request_pipeline")
    (op,) = migration.Migration.operations
    assert isinstance(op, migrations.AlterField) and op.name == "action"


def test_a_new_request_starts_with_the_defaults():
    req = RequestFactory()
    assert req.quote_status == "none" and req.value_range == "" and req.next_follow_up is None
    assert req.first_reply_at is None and req.source_page == req.utm_source == req.utm_medium == req.utm_campaign == ""


# --- source from the intake form ---------------------------------------------------------------------------


def test_the_source_is_saved_when_the_form_sends_it_and_blank_when_not(api, payload):
    sent = {
        **payload,
        "date": None,
        "time": None,
        "sourcePage": "/services/ai-erp",
        "utmSource": "newsletter",
        "utmMedium": "email",
        "utmCampaign": "spring",
    }
    created = post_request(api, sent)
    assert created.status_code == 201
    req = Request.objects.get(reference=created.json()["reference"])
    assert (req.source_page, req.utm_source, req.utm_medium, req.utm_campaign) == (
        "/services/ai-erp",
        "newsletter",
        "email",
        "spring",
    )
    plain = post_request(api, {**payload, "requestKey": str(uuid.uuid4()), "date": None, "time": None})
    req = Request.objects.get(reference=plain.json()["reference"])
    assert req.source_page == req.utm_source == req.utm_medium == req.utm_campaign == ""


def test_an_over_long_source_value_is_refused_not_cut_silently(api, payload):
    assert post_request(api, {**payload, "date": None, "time": None, "utmSource": "x" * 101}).status_code == 400


# --- changes go through update_request: events, audit, first reply ---------------------------------------


def test_pipeline_changes_write_an_event_and_an_audit_entry_with_before_and_after():
    owner = OwnerFactory()
    req = RequestFactory()
    follow_up = date(2026, 12, 20)
    services.update_request(
        req, quote_status="sent", value_range="50k_200k", next_follow_up=follow_up, set_follow_up=True, actor=owner
    )
    req.refresh_from_db()
    assert (req.quote_status, req.value_range, req.next_follow_up) == ("sent", "50k_200k", follow_up)
    entry = AuditEntry.objects.get(action="request.pipeline")
    assert entry.target_id == req.reference and entry.actor_label == owner.email
    assert entry.before == {"quote_status": "none", "value_range": "", "next_follow_up": None}
    assert entry.after == {"quote_status": "sent", "value_range": "50k_200k", "next_follow_up": "2026-12-20"}
    assert RequestEvent.objects.filter(request=req, event_type="pipeline_updated", actor=owner).count() == 1

    services.update_request(req, quote_status="sent", actor=owner)  # nothing changed: nothing written
    assert AuditEntry.objects.filter(action="request.pipeline").count() == 1
    services.update_request(req, next_follow_up=None, set_follow_up=True, value_range="", actor=owner)  # clears
    req.refresh_from_db()
    assert req.next_follow_up is None and req.value_range == ""
    assert AuditEntry.objects.filter(action="request.pipeline").count() == 2


def test_first_reply_is_set_once_by_the_first_status_change_or_note_and_not_by_assigning_or_the_quote():
    owner = OwnerFactory()
    req = RequestFactory()
    services.update_request(req, assigned_to=owner, assign=True, actor=owner)
    services.update_request(req, quote_status="sent", actor=owner)
    req.refresh_from_db()
    assert req.first_reply_at is None  # assigning and a quote change are not a reply
    services.update_request(req, status=req.status, actor=owner)  # same status: not a change
    req.refresh_from_db()
    assert req.first_reply_at is None
    services.update_request(req, internal_note="Called, will send the plan.", actor=owner)
    req.refresh_from_db()
    first = req.first_reply_at
    assert first is not None
    services.update_request(req, status="in_review", actor=owner)
    req.refresh_from_db()
    assert req.first_reply_at == first  # kept


def test_a_status_change_sets_first_reply_too():
    req = RequestFactory()
    services.update_request(req, status="in_review", actor=OwnerFactory())
    req.refresh_from_db()
    assert req.first_reply_at is not None


def admin_request(user):
    request = DjangoRequestFactory().post("/admin/leads/request/1/change/")
    request.user = user
    request.session = {}
    request._messages = SimpleNamespace(add=lambda *a, **k: None)
    return request


def test_the_admin_form_saves_pipeline_fields_through_the_service_and_audits_them():
    owner = OwnerFactory()
    req = RequestFactory()
    req.quote_status, req.next_follow_up = "accepted", date(2026, 12, 1)
    form = SimpleNamespace(changed_data=["quote_status", "next_follow_up"])
    RequestAdmin(Request, django_admin.site).save_model(admin_request(owner), req, form, True)
    stored = Request.objects.get(pk=req.pk)
    assert stored.quote_status == "accepted" and stored.next_follow_up == date(2026, 12, 1)
    entry = AuditEntry.objects.get(action="request.pipeline")
    assert entry.after == {"quote_status": "accepted", "next_follow_up": "2026-12-01"}
    assert RequestEvent.objects.filter(request=stored, event_type="pipeline_updated").exists()


# --- admin list filters --------------------------------------------------------------------------------


def test_the_admin_list_filters_by_quote_value_follow_up_and_source():
    sent = RequestFactory(quote_status="sent", value_range="gt_200k", utm_source="newsletter")
    won = RequestFactory(quote_status="accepted", value_range="lt_50k", next_follow_up=date(2026, 12, 5))
    plain = RequestFactory()
    root = UserFactory(is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(root)

    def refs(query):
        page = client.get("/admin/leads/request/" + query)
        assert page.status_code == 200, query
        return {r.reference for r in page.context["cl"].result_list}

    assert refs("?quote_status__exact=sent") == {sent.reference}
    assert refs("?value_range__exact=lt_50k") == {won.reference}
    assert refs("?utm_source=newsletter") == {sent.reference}
    assert refs("?next_follow_up__gte=2026-12-01&next_follow_up__lt=2026-12-31") == {won.reference}
    assert refs("") == {sent.reference, won.reference, plain.reference}
    assert refs("?q=newsletter") == {sent.reference}  # the source is searchable


# --- the customer sees none of it ----------------------------------------------------------------------


def test_the_customer_status_answer_has_only_the_public_fields(api):
    req = RequestFactory(
        email="visitor-a@example.test",
        quote_status="sent",
        value_range="gt_200k",
        utm_source="newsletter-secret-campaign",
        source_page="/private/landing",
        next_follow_up=date(2026, 12, 9),
        internal_note="Budget is large, push hard.",
    )
    answer = api.post(
        "/api/request-status",
        data=json.dumps({"reference": req.reference, "email": req.email}),
        content_type="application/json",
    )
    assert answer.status_code == 200
    body = answer.json()
    assert set(body) == {"reference", "kind", "status", "createdAt", "updatedAt", "appointment"}
    text = answer.content.decode()
    for secret in ("newsletter-secret-campaign", "/private/landing", "gt_200k", "sent", "2026-12-09", "push hard"):
        assert secret not in text.replace('"status": "pending_review"', ""), secret


def test_the_customer_account_views_carry_no_pipeline_field_or_value():
    owner = OwnerFactory()
    req = RequestFactory(quote_status="lost", value_range="lt_50k", utm_source="partner-x", source_page="/p")
    services.update_request(req, quote_status="accepted", status="in_review", actor=owner)
    data = MyRequestDetailSerializer(req).data
    assert not PRIVATE & set(data)
    flat = json.dumps(dict(data), default=str)
    assert "partner-x" not in flat and "accepted" not in flat and "lt_50k" not in flat
    assert {e["event_type"] for e in data["events"]} >= {"pipeline_updated", "status_changed"}  # type only, no values
    assert all(set(e) == {"event_type", "status", "created_at"} for e in data["events"])


def test_the_status_page_text_has_one_line_per_status_in_both_languages():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "frontend" / "components" / "RequestStatus.tsx").read_text()
    meanings = source.split("const meanings:Record<string,[string,string]>={", 1)[1].split("};", 1)[0]
    for status in Request.Status.values:
        assert f"{status}:['" in meanings, status
    assert "quote" not in meanings.lower() and "value" not in meanings.lower()


# --- numbers on the dashboard ----------------------------------------------------------------------------


def make(created_days_ago=1, reply_hours=None, utm="", quote="none"):
    created = timezone.now() - timedelta(days=created_days_ago)
    req = RequestFactory(utm_source=utm, quote_status=quote)
    Request.objects.filter(pk=req.pk).update(
        created_at=created, first_reply_at=created + timedelta(hours=reply_hours) if reply_hours is not None else None
    )
    return req


def test_quote_stages_count_every_stage_including_empty_ones():
    for quote in ("none", "none", "sent", "accepted"):
        RequestFactory(quote_status=quote)
    counts = {s["value"]: s["count"] for s in pipeline.quote_stage_counts()}
    assert counts == {"none": 2, "sent": 1, "accepted": 1, "lost": 0}


def test_first_reply_is_the_median_hours_of_the_last_30_days_and_counts_those_still_waiting():
    make(created_days_ago=2, reply_hours=2)
    make(created_days_ago=3, reply_hours=4)
    make(created_days_ago=4, reply_hours=30)
    make(created_days_ago=5)  # waiting
    make(created_days_ago=60, reply_hours=500)  # outside the window
    summary = pipeline.first_reply_summary()
    assert summary == {"median_hours": 4.0, "replied": 3, "waiting": 1}
    Request.objects.all().delete()
    assert pipeline.first_reply_summary() == {"median_hours": None, "replied": 0, "waiting": 0}


def test_win_rate_per_source_leaves_undecided_quotes_out_and_names_blank_sources_direct():
    for quote in ("accepted", "accepted", "lost", "sent", "none"):
        make(utm=" Newsletter ", quote=quote)  # trimmed and lower-cased
    make(utm="", quote="lost")
    make(utm="", quote="sent")
    make(utm="partner", quote="none")
    rows = {r["source"]: r for r in pipeline.win_rate_by_source()}
    assert rows["newsletter"] == {"source": "newsletter", "total": 5, "won": 2, "lost": 1, "rate": 67}
    assert rows["direct"] == {"source": "direct", "total": 2, "won": 0, "lost": 1, "rate": 0}
    assert rows["partner"]["rate"] is None  # nothing decided yet: no rate, not 0
    assert [r["source"] for r in pipeline.win_rate_by_source()][0] == "newsletter"  # most requests first


def test_the_dashboard_shows_the_numbers():
    make(created_days_ago=2, reply_hours=6, utm="newsletter", quote="accepted")
    root = UserFactory(is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(root)
    page = client.get("/admin/")
    html = page.content.decode()
    assert page.status_code == 200 and "Quotes by stage" in html and "6.0 hours" in html
    assert "Win rate by source" in html and "newsletter" in html and "100%" in html
