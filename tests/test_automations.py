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


def test_no_action_can_contact_a_customer(client, auth_headers):
    meta = client.get("/api/v1/automations/meta", headers=auth_headers).json()

    assert meta["delivery"]["external_delivery_available"] is False
    # The binding constraint of this workstream, asserted rather than
    # merely documented: if someone adds an action that sends anything,
    # this test fails and they have to come and change it deliberately.
    assert set(meta["actions"]) == {
        "create_notification",
        "create_project_from_quote",
        "create_task",
        "draft_message",
    }
    assert set(meta["actions"]) == set(ACTION_TYPES)


def test_meta_lists_every_trigger_with_its_kind(client, auth_headers):
    meta = client.get("/api/v1/automations/meta", headers=auth_headers).json()
    by_key = {t["key"]: t for t in meta["triggers"]}

    assert len(by_key) == 9
    assert by_key["quote.approved"]["kind"] == "event"
    assert by_key["quote.expiring"]["kind"] == "scan"
    assert by_key["project.starting"]["kind"] == "scan"


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
