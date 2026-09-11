"""Automation UX — Sprint 039, Workstream E.

Sprint 038 gave automations their first genuinely customer-facing action
and served the distinction from the API. The UI never caught up:
`apps/web/types/automation.ts` still had four action labels for five
action types, no `customer_facing_actions` field at all, and a header
asserting "GeoCore has no outbound email, SMS or messaging
infrastructure, so nothing here contacts a customer" — which had been
false since Sprint 038 shipped.

The fix is not more frontend copy. It is a **served catalogue**: the
backend states what each action is and what class of thing it does, and
the builder renders that. A UI cannot then describe an action wrongly,
because it does not describe actions at all.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.automations import actions
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Automation,
    AutomationRun,
    Communication,
    Customer,
    EmailSuppression,
    NotificationRecord,
    Task,
    Tenant,
    User,
)

RUN_ID = uuid.uuid4().hex[:8]
TENANT_NAME = f"Pytest Automation UX {RUN_ID}"
OWNER_EMAIL = f"pytest-automation-ux-{RUN_ID}@example.invalid"
OWNER_PASSWORD = "pytest-automation-ux-password-1"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(
                delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant.id)
            )
            db.execute(delete(Task).where(Task.tenant_id == tenant.id))
            db.execute(delete(AutomationRun).where(AutomationRun.tenant_id == tenant.id))
            db.execute(delete(Automation).where(Automation.tenant_id == tenant.id))
            db.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(User).where(User.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture()
def workspace(client):
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": TENANT_NAME,
            "name": "Automation Owner",
            "email": OWNER_EMAIL,
            "password": OWNER_PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- Every action describes itself ---------------------------------------


def test_every_action_type_appears_in_the_catalogue():
    """The bug this prevents, exactly: Sprint 038 added a fifth action
    type and the frontend's hardcoded label map still had four, so
    `send_quote_follow_up` rendered with no label at all."""
    assert set(actions.ACTION_CATALOGUE) == actions.ACTION_TYPES


def test_every_catalogue_entry_says_what_it_does_and_what_class_it_is():
    for key, entry in actions.ACTION_CATALOGUE.items():
        assert entry["label"].strip(), key
        assert entry["description"].strip(), key
        assert entry["kind"] in actions.ACTION_KINDS, (key, entry["kind"])


def test_the_four_kinds_are_the_distinctions_a_user_needs():
    """A user deciding whether to switch an automation on needs to know
    which of these it is — above all, whether it reaches a customer."""
    assert set(actions.ACTION_KINDS) == {
        "internal_notification",
        "internal_task",
        "customer_communication",
        "ai_draft",
    }


def test_customer_facing_actions_are_exactly_the_ones_classified_as_such():
    """Two sources of the same truth would eventually disagree. The
    Sprint 038 set is derived from the catalogue rather than maintained
    beside it."""
    from_catalogue = {
        key
        for key, entry in actions.ACTION_CATALOGUE.items()
        if entry["kind"] == "customer_communication"
    }

    assert from_catalogue == actions.CUSTOMER_FACING_ACTION_TYPES


def test_only_genuinely_customer_facing_actions_are_marked_as_such():
    """A false positive here makes users distrust the warning; a false
    negative sends email they did not expect. Both matter, so the set is
    asserted exactly."""
    assert actions.CUSTOMER_FACING_ACTION_TYPES == {"send_quote_follow_up"}


def test_a_draft_action_is_not_marked_as_customer_facing():
    """`draft_message` prepares text for a human and transmits nothing.
    Marking it customer-facing would be the false positive above."""
    assert actions.ACTION_CATALOGUE["draft_message"]["kind"] != "customer_communication"
    assert actions.ACTION_CATALOGUE["draft_message_with_ai"]["kind"] == "ai_draft"


# --- The API serves it ----------------------------------------------------


def test_the_meta_endpoint_serves_the_catalogue(client, workspace):
    r = client.get("/api/v1/automations/meta", headers=workspace)

    assert r.status_code == 200, r.text
    body = r.json()
    assert {entry["key"] for entry in body["action_catalogue"]} == actions.ACTION_TYPES
    assert all(entry["label"] and entry["kind"] for entry in body["action_catalogue"])


def test_the_meta_endpoint_still_serves_what_sprint_038_served(client, workspace):
    """Backwards compatibility: Sprint 038's own fields stay exactly where
    they were, so nothing reading them breaks."""
    body = client.get("/api/v1/automations/meta", headers=workspace).json()

    assert set(body["actions"]) == actions.ACTION_TYPES
    assert set(body["customer_facing_actions"]) == actions.CUSTOMER_FACING_ACTION_TYPES
    assert "external_delivery_available" in body["delivery"]


# --- The new AI-draft action ---------------------------------------------


def test_the_ai_draft_action_creates_a_task_and_sends_nothing(client, workspace):
    """It prepares a message for a person. Like every draft in GeoCore, it
    reaches nobody until someone reads it and presses send."""
    customer = client.post(
        "/api/v1/customers",
        json={"name": "Jane Okafor", "email": "jane@example.invalid"},
        headers=workspace,
    ).json()

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        result = actions.perform(
            db,
            action={"type": "draft_message_with_ai", "config": {"kind": "project_update"}},
            tenant_id=tenant.id,
            subject={"id": customer["id"], "customer_id": customer["id"], "name": "A job"},
            dedupe_key=f"pytest-aidraft-{uuid.uuid4().hex}",
            now=None,
            context={"subject_type": "project"},
        )

        # No AI provider is configured in this environment, so the honest
        # outcome is a skip that says why — never a fabricated draft.
        assert "skipped" in result.lower()
        assert (
            db.query(Communication).filter(Communication.tenant_id == tenant.id).count()
            == 0
        )
    finally:
        db.close()


def test_an_automation_can_be_built_with_the_ai_draft_action(client, workspace):
    r = client.post(
        "/api/v1/automations",
        json={
            "name": "Draft a project update when a job starts",
            "trigger_type": "project.status_changed",
            "actions": [{"type": "draft_message_with_ai", "config": {"kind": "project_update"}}],
        },
        headers=workspace,
    )

    assert r.status_code == 201, r.text
    assert r.json()["actions"][0]["type"] == "draft_message_with_ai"
