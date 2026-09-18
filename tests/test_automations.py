"""The automation engine — Sprint 036, Workstream G.

Three properties this file exists to guarantee, because each of them is a
promise the product makes to a user who has handed it a rule:

1. An automation can never break the thing that triggered it.
2. Every attempt is visible — succeeded, skipped with a reason, or failed
   with the message.
3. Running twice does the work once.

Plus the honesty constraint the sprint contract turns on: no action
reaches a customer, because GeoCore has no channel to reach one through.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.automations.actions import ACTION_TYPES
from app.automations.conditions import evaluate
from app.automations.engine import automation_engine
from app.automations.scan import automation_scanner
from app.automations.subjects import render
from app.database.database import SessionLocal
from app.database.models import (
    Automation,
    AutomationRun,
    NotificationRecord,
    Project,
    Quote,
    QuoteItem,
    Task,
)

RUN_ID = uuid.uuid4().hex[:8]
TEST_POSTCODE = f"PYA36{RUN_ID[:5]}".upper()
TEST_PREFIX = f"Pytest Automations {RUN_ID}"


def _cleanup():
    db = SessionLocal()
    try:
        automation_ids = select(Automation.id).where(Automation.name.like(f"{TEST_PREFIX}%"))
        db.execute(delete(AutomationRun).where(AutomationRun.automation_id.in_(automation_ids)))
        db.execute(delete(Automation).where(Automation.name.like(f"{TEST_PREFIX}%")))
        db.execute(delete(Task).where(Task.title.like(f"%{RUN_ID}%")))
        db.execute(delete(NotificationRecord).where(NotificationRecord.title.like(f"%{RUN_ID}%")))

        quote_ids = select(Quote.id).where(Quote.postcode == TEST_POSTCODE)
        db.execute(delete(Project).where(Project.quote_id.in_(quote_ids)))
        db.execute(delete(Project).where(Project.name.like(f"{TEST_PREFIX}%")))
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
        db.execute(delete(Quote).where(Quote.postcode == TEST_POSTCODE))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


def _automation(client, auth_headers, **overrides):
    payload = {
        "name": f"{TEST_PREFIX} rule",
        "trigger_type": "quote.approved",
        "conditions": [],
        "actions": [
            {
                "type": "create_task",
                "config": {"title": f"Chase {{customer_name}} {RUN_ID}", "due_in_days": 1},
            }
        ],
    }
    payload.update(overrides)
    r = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _general_quote(client, auth_headers, **overrides):
    payload = {
        "title": f"{TEST_PREFIX} quote",
        "trade": "roofing",
        "site_postcode": TEST_POSTCODE,
        "lines": [{"description": "Re-roof", "quantity": 1, "unit": "job", "unit_price": 6000}],
    }
    payload.update(overrides)
    r = client.post("/api/v1/quotes", json=payload, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _runs(client, auth_headers, automation_id):
    r = client.get(f"/api/v1/automations/runs?automation_id={automation_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


# --- Vocabulary and honesty ----------------------------------------------


def test_internal_actions_are_exactly_the_original_four_plus_one_customer_facing(client, auth_headers):
    """Sprint 036's binding constraint ("no action can contact a
    customer") is now Sprint 038's binding constraint that the line
    between internal and customer-facing actions is exact and asserted,
    not just documented: if someone adds a new action, this test fails
    and they have to come mark it one or the other deliberately."""
    meta = client.get("/api/v1/automations/meta", headers=auth_headers).json()

    assert set(meta["actions"]) == {
        "create_notification",
        "create_project_from_quote",
        "create_task",
        "draft_message",
        "send_quote_follow_up",
    }
    assert set(meta["actions"]) == set(ACTION_TYPES)
    assert set(meta["customer_facing_actions"]) == {"send_quote_follow_up"}


def test_delivery_availability_reflects_whether_a_provider_is_actually_configured(
    client, auth_headers, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "resend_api_key", None)
    unconfigured = client.get("/api/v1/automations/meta", headers=auth_headers).json()
    assert unconfigured["delivery"]["external_delivery_available"] is False

    monkeypatch.setattr(settings, "resend_api_key", "re_test_fake_key")
    configured = client.get("/api/v1/automations/meta", headers=auth_headers).json()
    assert configured["delivery"]["external_delivery_available"] is True


def test_meta_lists_every_trigger_with_its_kind(client, auth_headers):
    meta = client.get("/api/v1/automations/meta", headers=auth_headers).json()
    by_key = {t["key"]: t for t in meta["triggers"]}

    # GeoCore Premium OS Plan 04 (Sprint 043) added 6 financial/variation
    # triggers (variation.created/sent/approved/rejected, cost.added,
    # margin_risk.detected) to the original 9. Plan 05 (Sprint 044) added
    # 7 more procurement triggers (material_requirement.created,
    # purchase_order.approved/ordered/partially_received/received,
    # delivery.overdue, material.allocated).
    assert len(by_key) == 22
    assert by_key["quote.approved"]["kind"] == "event"
    assert by_key["quote.expiring"]["kind"] == "scan"
    assert by_key["project.starting"]["kind"] == "scan"
    assert by_key["variation.approved"]["kind"] == "event"
    assert by_key["margin_risk.detected"]["kind"] == "event"
    assert by_key["purchase_order.approved"]["kind"] == "event"
    assert by_key["delivery.overdue"]["kind"] == "scan"


def test_templates_are_definitions_not_rows(client, auth_headers):
    templates = client.get("/api/v1/automations/templates", headers=auth_headers).json()
    assert len(templates) >= 5

    # Listing templates must never create anything in the workspace.
    listed = client.get("/api/v1/automations", headers=auth_headers).json()
    assert all(a["template_key"] is None for a in listed if a["name"].startswith(TEST_PREFIX))


def test_activating_a_template_creates_a_real_editable_rule(client, auth_headers):
    r = client.post(
        "/api/v1/automations/templates",
        json={"template_key": "approved_quote_to_project"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    created = r.json()

    assert created["template_key"] == "approved_quote_to_project"
    assert created["trigger_type"] == "quote.approved"
    assert created["actions"][0]["type"] == "create_project_from_quote"

    patched = client.patch(
        f"/api/v1/automations/{created['id']}",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    client.delete(f"/api/v1/automations/{created['id']}", headers=auth_headers)


# --- Validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"trigger_type": "quote.telepathy"},
        {"actions": []},
        {"actions": [{"type": "send_email", "config": {}}]},
        {"actions": [{"type": "create_task", "config": {"webhook_url": "http://x"}}]},
        {"conditions": [{"field": "status", "op": "regex", "value": ".*"}]},
    ],
)
def test_rejects_invalid_rules(client, auth_headers, override):
    payload = {
        "name": f"{TEST_PREFIX} invalid",
        "trigger_type": "quote.approved",
        "actions": [{"type": "create_task", "config": {"title": "x"}}],
    }
    payload.update(override)
    r = client.post("/api/v1/automations", json=payload, headers=auth_headers)
    assert r.status_code == 422, r.text


# --- Execution ------------------------------------------------------------


def test_an_event_trigger_fires_and_records_a_successful_run(client, auth_headers):
    automation = _automation(client, auth_headers)
    quote = _general_quote(client, auth_headers)

    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    runs = _runs(client, auth_headers, automation["id"])
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["subject_id"] == quote["id"]
    assert "task created" in runs[0]["detail"]

    tasks = client.get("/api/v1/tasks", headers=auth_headers).json()
    assert any(RUN_ID in t["title"] for t in tasks)


def test_a_stone_quote_fires_quote_created_exactly_like_a_general_one(client, auth_headers):
    # Stone is a specialist workflow inside GeoCore, not a separate product,
    # and it has its own creation route (POST /quote, the calculator) with its
    # own payload shape. A rule that fired for general quotes and silently did
    # nothing for stone ones would be the worst failure this feature can have:
    # the user sees no error, only work that quietly never happened. That is
    # why dispatch lives in the quote service rather than on one route.
    automation = _automation(client, auth_headers, trigger_type="quote.created")

    r = client.post(
        "/api/v1/quote",
        json={
            "customer": f"{TEST_PREFIX} stone customer",
            "material": "Calacatta Gold",
            "thickness": "20mm",
            "kitchen_length": 3,
            "postcode": TEST_POSTCODE,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    quote = r.json()

    runs = _runs(client, auth_headers, automation["id"])
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["subject_id"] == quote["id"]

    tasks = client.get("/api/v1/tasks", headers=auth_headers).json()
    assert any(RUN_ID in t["title"] for t in tasks)


def test_conditions_that_do_not_match_record_a_skip_with_a_reason(client, auth_headers):
    automation = _automation(
        client,
        auth_headers,
        conditions=[{"field": "trade", "op": "eq", "value": "kitchen"}],
    )
    quote = _general_quote(client, auth_headers)  # trade is "roofing"

    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    runs = _runs(client, auth_headers, automation["id"])
    assert len(runs) == 1
    assert runs[0]["status"] == "skipped"
    assert runs[0]["detail"] == "conditions not met"


def test_a_disabled_automation_does_not_run(client, auth_headers):
    automation = _automation(client, auth_headers, enabled=False)
    quote = _general_quote(client, auth_headers)

    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    assert _runs(client, auth_headers, automation["id"]) == []


def test_running_the_same_trigger_twice_does_the_work_once(client, auth_headers, db):
    automation = _automation(client, auth_headers)
    quote = _general_quote(client, auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    # Re-dispatch the identical event directly against the engine — the
    # same thing a retried request or a duplicated webhook would do.
    subject = {"id": quote["id"], "customer_name": "", "status": "approved"}
    automation_engine.run_for_subject(
        db,
        tenant_id=uuid.UUID(str(_tenant_id(client, auth_headers))),
        trigger_type="quote.approved",
        subject=subject,
        now=datetime.now(timezone.utc),
    )

    tasks = client.get("/api/v1/tasks?limit=200", headers=auth_headers).json()
    assert sum(1 for t in tasks if RUN_ID in t["title"]) == 1

    succeeded = [r for r in _runs(client, auth_headers, automation["id"]) if r["status"] == "succeeded"]
    assert len(succeeded) == 1


def test_a_failing_action_records_a_failure_and_does_not_break_approval(client, auth_headers):
    # create_project_from_quote against a quote that will not be approved
    # at the time this rule fires: quote.created fires while the quote is
    # still a draft, so handoff legitimately refuses.
    automation = _automation(
        client,
        auth_headers,
        trigger_type="quote.created",
        actions=[{"type": "create_project_from_quote", "config": {}}],
    )

    # The user's own action must still succeed.
    quote = _general_quote(client, auth_headers)
    assert quote["status"] == "draft"

    runs = _runs(client, auth_headers, automation["id"])
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "not approved" in runs[0]["detail"]


def test_approved_quote_to_project_template_end_to_end(client, auth_headers):
    activated = client.post(
        "/api/v1/automations/templates",
        json={"template_key": "approved_quote_to_project"},
        headers=auth_headers,
    ).json()

    customer = client.post(
        "/api/v1/customers", json={"name": f"{TEST_PREFIX} customer"}, headers=auth_headers
    ).json()
    quote = _general_quote(client, auth_headers, customer_id=customer["id"])
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    runs = _runs(client, auth_headers, activated["id"])
    assert runs and runs[0]["status"] == "succeeded"

    projects = client.get("/api/v1/projects?limit=100", headers=auth_headers).json()
    assert any(p["quote_id"] == quote["id"] for p in projects)

    client.delete(f"/api/v1/automations/{activated['id']}", headers=auth_headers)


def test_customer_created_trigger_fires(client, auth_headers):
    automation = _automation(
        client,
        auth_headers,
        trigger_type="customer.created",
        actions=[
            {"type": "create_task", "config": {"title": f"First contact: {{name}} {RUN_ID}"}}
        ],
    )
    client.post(
        "/api/v1/customers",
        json={"name": f"{TEST_PREFIX} lead"},
        headers=auth_headers,
    )

    runs = _runs(client, auth_headers, automation["id"])
    assert len(runs) == 1 and runs[0]["status"] == "succeeded"


# --- Scan triggers --------------------------------------------------------


def test_expiring_quote_scan_creates_one_task_however_often_it_runs(
    client, auth_headers, db
):
    client.post(
        "/api/v1/automations/templates",
        json={"template_key": "follow_up_unanswered_quotes"},
        headers=auth_headers,
    )
    expiry = date.today() + timedelta(days=2)
    quote = _general_quote(client, auth_headers, valid_until=expiry.isoformat())
    client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)

    now = datetime.now(timezone.utc)
    first = automation_scanner.run(db, now=now)
    second = automation_scanner.run(db, now=now + timedelta(hours=6))

    assert first.runs_succeeded == 1
    assert second.runs_succeeded == 0

    tasks = client.get("/api/v1/tasks?limit=200", headers=auth_headers).json()
    assert sum(1 for t in tasks if t["title"].startswith("Follow up quote")) >= 1

    _delete_template_rules(client, auth_headers)


def test_expiring_quote_scan_ignores_a_quote_that_is_not_yet_due(client, auth_headers, db):
    client.post(
        "/api/v1/automations/templates",
        json={"template_key": "follow_up_unanswered_quotes"},
        headers=auth_headers,
    )
    quote = _general_quote(
        client, auth_headers, valid_until=(date.today() + timedelta(days=60)).isoformat()
    )
    client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)

    result = automation_scanner.run(db, now=datetime.now(timezone.utc))
    assert result.runs_succeeded == 0

    _delete_template_rules(client, auth_headers)


def test_expiring_quote_scan_ignores_an_approved_quote(client, auth_headers, db):
    client.post(
        "/api/v1/automations/templates",
        json={"template_key": "follow_up_unanswered_quotes"},
        headers=auth_headers,
    )
    quote = _general_quote(
        client, auth_headers, valid_until=(date.today() + timedelta(days=1)).isoformat()
    )
    client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    result = automation_scanner.run(db, now=datetime.now(timezone.utc))
    assert result.runs_succeeded == 0

    _delete_template_rules(client, auth_headers)


# --- send_quote_follow_up (Sprint 038, Phase 3) ---------------------------
#
# The provider is always faked here (a MagicMock swapped for the real
# delivery_service singleton, same pattern tests/test_billing.py uses for
# Stripe) — no real network call, and no dependency on RESEND_API_KEY
# being configured in this test environment.


def _customer_with_email(client, auth_headers, email: str) -> dict:
    r = client.post(
        "/api/v1/customers", json={"name": f"{TEST_PREFIX} customer", "email": email}, headers=auth_headers
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_send_quote_follow_up_action_emails_the_linked_customer(client, auth_headers, db, monkeypatch):
    from unittest.mock import MagicMock

    import app.communications.service as communications_service_module
    from app.database.models import Communication

    fake_communication = Communication(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), status="sent", message_type="quote_follow_up",
        recipient="customer@example.invalid", sender_identity="x", subject="x", body_html="x",
        body_text="x", dedupe_key="x",
    )
    fake_delivery = MagicMock()
    fake_delivery.send.return_value = fake_communication
    monkeypatch.setattr(communications_service_module, "delivery_service", fake_delivery)

    client.post(
        "/api/v1/automations/templates",
        json={"template_key": "quote_follow_up_email"},
        headers=auth_headers,
    )
    customer = _customer_with_email(client, auth_headers, f"{TEST_PREFIX.lower().replace(' ', '-')}@example.invalid")
    expiry = date.today() + timedelta(days=2)
    quote = _general_quote(
        client, auth_headers, valid_until=expiry.isoformat(), customer_id=customer["id"]
    )
    client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)

    result = automation_scanner.run(db, now=datetime.now(timezone.utc))

    assert result.runs_succeeded == 1
    fake_delivery.send.assert_called_once()
    call_kwargs = fake_delivery.send.call_args.kwargs
    assert call_kwargs["recipient"] == customer["email"]
    assert call_kwargs["quote_id"] == uuid.UUID(quote["id"])

    _delete_template_rules(client, auth_headers)


def test_send_quote_follow_up_action_skips_a_quote_with_no_customer(client, auth_headers, db, monkeypatch):
    from unittest.mock import MagicMock

    import app.communications.service as communications_service_module

    fake_delivery = MagicMock()
    monkeypatch.setattr(communications_service_module, "delivery_service", fake_delivery)

    client.post(
        "/api/v1/automations/templates",
        json={"template_key": "quote_follow_up_email"},
        headers=auth_headers,
    )
    expiry = date.today() + timedelta(days=2)
    quote = _general_quote(client, auth_headers, valid_until=expiry.isoformat())
    client.post(f"/api/v1/quotes/{quote['id']}/send", headers=auth_headers)

    result = automation_scanner.run(db, now=datetime.now(timezone.utc))

    # The run itself still "succeeds" (the action ran and returned a
    # skip reason, not an exception) — it just never touches delivery.
    assert result.runs_succeeded == 1
    fake_delivery.send.assert_not_called()

    _delete_template_rules(client, auth_headers)


def test_project_starting_scan_notifies_once(client, auth_headers, db):
    client.post(
        "/api/v1/automations/templates",
        json={"template_key": "project_starts_tomorrow"},
        headers=auth_headers,
    )
    project = client.post(
        "/api/v1/projects",
        json={
            "name": f"{TEST_PREFIX} starting job",
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
        },
        headers=auth_headers,
    ).json()
    assert project["start_date"] is not None

    now = datetime.now(timezone.utc)
    assert automation_scanner.run(db, now=now).runs_succeeded == 1
    assert automation_scanner.run(db, now=now).runs_succeeded == 0

    _delete_template_rules(client, auth_headers)


# --- Isolation and permissions -------------------------------------------


def test_another_tenant_cannot_see_or_edit_an_automation(
    client, auth_headers, other_tenant_auth_headers
):
    automation = _automation(client, auth_headers)

    assert (
        client.get(f"/api/v1/automations/{automation['id']}", headers=other_tenant_auth_headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/automations/{automation['id']}",
            json={"enabled": False},
            headers=other_tenant_auth_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/automations/{automation['id']}", headers=other_tenant_auth_headers
        ).status_code
        == 404
    )
    assert client.get("/api/v1/automations", headers=other_tenant_auth_headers).json() == []


def test_another_tenants_runs_are_invisible(client, auth_headers, other_tenant_auth_headers):
    automation = _automation(client, auth_headers)
    quote = _general_quote(client, auth_headers)
    client.post(f"/api/v1/quotes/{quote['id']}/approve", headers=auth_headers)

    assert client.get("/api/v1/automations/runs", headers=other_tenant_auth_headers).json() == []
    # Asking for a specific automation you don't own is a 404, not an
    # empty list — an empty list would quietly confirm nothing while
    # reading as "no history".
    assert (
        client.get(
            f"/api/v1/automations/runs?automation_id={automation['id']}",
            headers=other_tenant_auth_headers,
        ).status_code
        == 404
    )


# --- Pure units -----------------------------------------------------------


def test_conditions_fail_closed_on_an_unknown_field():
    # A rule referencing a field the subject doesn't expose must not run
    # its actions: silently ignoring the condition would fire a rule the
    # author believes is narrowly scoped.
    assert evaluate([{"field": "secret", "op": "eq", "value": 1}], {"status": "draft"}) is False


def test_conditions_never_compare_against_a_missing_value():
    assert evaluate([{"field": "total", "op": "gt", "value": 100}], {"total": None}) is False


def test_render_cannot_traverse_attributes():
    # Not str.format(): "{x.__class__}" must stay literal text rather than
    # reaching into an object.
    assert render("{x.__class__}", {"x": "a"}) == "{x.__class__}"
    assert render("{name} owes {amount}", {"name": "Ada", "amount": None}) == "Ada owes "


# --- helpers --------------------------------------------------------------


def _tenant_id(client, auth_headers):
    return client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"]


def _delete_template_rules(client, auth_headers):
    for automation in client.get("/api/v1/automations", headers=auth_headers).json():
        if automation["template_key"]:
            client.delete(f"/api/v1/automations/{automation['id']}", headers=auth_headers)
