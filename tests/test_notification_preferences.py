"""Server-side notification preferences — Sprint 039, Workstream B.

Sprint 036 shipped this screen as four `localStorage` keys and said so
honestly in its own docstring: "a per-user server-side preference table is
genuine follow-up work... shipping a server-backed setting that nothing
reads would be worse than shipping a local one that something does."

This is that table, and the thing that reads it. The contract:

  * preferences are per user, per tenant, per category;
  * enforcement happens **server-side, at the point a notification is
    created** — never by hiding rows in the client;
  * defaults preserve today's behaviour exactly (in-app on, email off), so
    nobody's experience silently changes and nobody starts receiving email
    they did not ask for;
  * a tenant-wide broadcast has no addressee, so no preference applies.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    EmailSuppression,
    NotificationRecord,
    Task,
    Tenant,
    User,
)
from app.notifications import categories, preferences

RUN_ID = uuid.uuid4().hex[:8]
TENANT_NAME = f"Pytest Notif Prefs {RUN_ID}"
OWNER_EMAIL = f"pytest-notif-prefs-{RUN_ID}@example.invalid"
OWNER_PASSWORD = "pytest-notif-prefs-password-1"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            # Ordered children-before-parents, same convention as
            # tests/conftest.py's own teardown. `notification_preferences`
            # and `pipeline_stages` are absent on purpose — both cascade
            # with their tenant (see their models' docstrings).
            db.execute(delete(Task).where(Task.tenant_id == tenant.id))
            db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(
                delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant.id)
            )
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
            "name": "Prefs Owner",
            "email": OWNER_EMAIL,
            "password": OWNER_PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == OWNER_EMAIL).first()
        return headers, user.tenant_id, user.id
    finally:
        db.close()


# --- The vocabulary -------------------------------------------------------


def test_every_category_is_one_something_actually_produces():
    """The Sprint 036 honesty rule, carried forward: a preference that
    controls nothing is a mock with a database table behind it. Every
    category here maps to a notification GeoCore genuinely creates."""
    assert {category.key for category in categories.CATEGORIES} == {
        "quote_activity",
        "project_activity",
        "customer_activity",
        "task_assignment",
        "automation_outcome",
        "communication_failure",
    }


def test_a_category_carries_a_label_and_a_description_for_the_settings_screen():
    for category in categories.CATEGORIES:
        assert category.label.strip(), category.key
        assert category.description.strip(), category.key


def test_an_automations_subject_maps_onto_a_category():
    assert categories.for_subject_type("quote") == "quote_activity"
    assert categories.for_subject_type("project") == "project_activity"
    assert categories.for_subject_type("customer") == "customer_activity"


def test_an_unknown_subject_type_maps_to_nothing_rather_than_guessing():
    """A notification whose category cannot be determined is delivered
    rather than silently dropped — see preferences.allows()."""
    assert categories.for_subject_type("spaceship") is None


# --- Defaults preserve today's behaviour ---------------------------------


def test_a_user_who_has_never_touched_settings_gets_todays_behaviour(workspace):
    """In-app on for everything (exactly what the localStorage card
    defaulted to), email off for everything — nobody starts receiving mail
    they did not ask for."""
    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        resolved = preferences.resolve(db, tenant_id, user_id)
    finally:
        db.close()

    assert set(resolved) == {category.key for category in categories.CATEGORIES}
    assert all(pref["in_app"] for pref in resolved.values())
    assert not any(pref["email"] for pref in resolved.values())


def test_the_api_serves_the_categories_with_their_current_settings(client, workspace):
    headers, _, _ = workspace

    r = client.get("/api/v1/notifications/preferences", headers=headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert {row["category"] for row in body} == {
        category.key for category in categories.CATEGORIES
    }
    assert all(row["label"] and row["description"] for row in body)


# --- Persisting a change --------------------------------------------------


def test_turning_a_category_off_persists_across_requests(client, workspace):
    headers, _, _ = workspace

    r = client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "quote_activity", "in_app": False, "email": False}]},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    again = client.get("/api/v1/notifications/preferences", headers=headers).json()
    quote_activity = next(row for row in again if row["category"] == "quote_activity")
    assert quote_activity["in_app"] is False


def test_updating_one_category_leaves_the_others_alone(client, workspace):
    headers, _, _ = workspace

    client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "quote_activity", "in_app": False, "email": False}]},
        headers=headers,
    )

    body = client.get("/api/v1/notifications/preferences", headers=headers).json()
    others = [row for row in body if row["category"] != "quote_activity"]
    assert all(row["in_app"] for row in others)


def test_an_unknown_category_is_rejected_rather_than_silently_stored(client, workspace):
    headers, _, _ = workspace

    r = client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "not-a-category", "in_app": False, "email": False}]},
        headers=headers,
    )

    assert r.status_code == 422


def test_one_users_preferences_never_affect_another_user_in_the_same_tenant(
    client, workspace
):
    """Preferences are per user, not per workspace — muting your own quote
    notifications must not mute your colleague's."""
    headers, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        colleague = crud.create_user(
            db,
            id=uuid.uuid4(),
            name="Colleague",
            email=f"pytest-colleague-{RUN_ID}@example.invalid",
            password_hash="x",
            role="Staff",
            tenant_id=tenant_id,
        )
        colleague_id = colleague.id
    finally:
        db.close()

    client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "quote_activity", "in_app": False, "email": False}]},
        headers=headers,
    )

    db = SessionLocal()
    try:
        assert preferences.allows(db, tenant_id, user_id, "quote_activity", "in_app") is False
        assert preferences.allows(db, tenant_id, colleague_id, "quote_activity", "in_app") is True
    finally:
        db.close()


def test_preferences_require_authentication(client):
    assert client.get("/api/v1/notifications/preferences").status_code in (401, 403)


# --- Enforcement, server-side --------------------------------------------


def test_allows_defaults_to_true_for_a_user_with_no_stored_preference(workspace):
    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        assert preferences.allows(db, tenant_id, user_id, "project_activity", "in_app") is True
        assert preferences.allows(db, tenant_id, user_id, "project_activity", "email") is False
    finally:
        db.close()


def test_a_notification_a_user_muted_is_never_created_at_all(client, workspace):
    """Server-side enforcement, not client-side hiding: the row must not
    exist, because a row that exists is a row an unread count can find and
    a future client can render."""
    headers, tenant_id, user_id = workspace
    client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "quote_activity", "in_app": False, "email": False}]},
        headers=headers,
    )

    db = SessionLocal()
    try:
        created = preferences.notify(
            db,
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            category="quote_activity",
            title="A quote was approved",
            message="Quote 123 was approved.",
            dedupe_key=f"pytest-muted-{uuid.uuid4().hex}",
        )
        assert created is None

        remaining = (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .count()
        )
        assert remaining == 0
    finally:
        db.close()


def test_a_notification_a_user_still_wants_is_created(workspace):
    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        created = preferences.notify(
            db,
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            category="quote_activity",
            title="A quote was approved",
            message="Quote 123 was approved.",
            dedupe_key=f"pytest-kept-{uuid.uuid4().hex}",
        )

        assert created is not None
        assert created.title == "A quote was approved"
    finally:
        db.close()


def test_a_tenant_wide_broadcast_is_never_filtered_by_anyones_preference(
    client, workspace
):
    """A broadcast has no addressee, so there is no one whose preference
    could apply. Muting everything must not silence the whole workspace."""
    headers, tenant_id, _ = workspace
    client.put(
        "/api/v1/notifications/preferences",
        json={
            "preferences": [
                {"category": category.key, "in_app": False, "email": False}
                for category in categories.CATEGORIES
            ]
        },
        headers=headers,
    )

    db = SessionLocal()
    try:
        created = preferences.notify(
            db,
            tenant_id=tenant_id,
            recipient_user_id=None,
            category="quote_activity",
            title="Workspace-wide notice",
            message="Everyone sees this.",
            dedupe_key=f"pytest-broadcast-{uuid.uuid4().hex}",
        )

        assert created is not None
    finally:
        db.close()


def test_a_notification_with_no_known_category_is_delivered_rather_than_dropped(
    workspace,
):
    """Failing open is the right default here: a category this build has
    not been taught about must not silently swallow a user's notification."""
    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        created = preferences.notify(
            db,
            tenant_id=tenant_id,
            recipient_user_id=user_id,
            category=None,
            title="Something happened",
            message="No category for this one.",
            dedupe_key=f"pytest-uncategorised-{uuid.uuid4().hex}",
        )

        assert created is not None
    finally:
        db.close()


# --- Enforcement at the real notification paths --------------------------
#
# The tests above prove `notify()` honours a preference. These prove the
# paths that actually create notifications go through it, which is the
# difference between a working feature and a well-tested dead end.


def _automation_notification(db, tenant_id, user_id, subject_type="quote"):
    """Run the automation engine's own create_notification action, exactly
    as a dispatched rule would."""
    from app.automations import actions

    return actions.perform(
        db,
        action={
            "type": "create_notification",
            "config": {"title": "A quote was approved", "message": "Quote {title}."},
        },
        tenant_id=tenant_id,
        subject={"id": str(uuid.uuid4()), "title": "Kitchen", "assigned_user_id": str(user_id)},
        dedupe_key=f"pytest-automation-{uuid.uuid4().hex}",
        now=None,
        context={"subject_type": subject_type},
    )


def test_an_automation_notification_honours_the_recipients_preference(client, workspace):
    """The Sprint 036 screen filtered rendering. This proves Sprint 039
    stops the row being written at all — through the real automation
    action, not through notify() directly."""
    headers, tenant_id, user_id = workspace
    client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "quote_activity", "in_app": False, "email": False}]},
        headers=headers,
    )

    db = SessionLocal()
    try:
        result = _automation_notification(db, tenant_id, user_id, subject_type="quote")

        assert "preference" in result.lower()
        assert (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_an_automation_notification_is_created_when_the_category_is_left_on(workspace):
    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        result = _automation_notification(db, tenant_id, user_id, subject_type="quote")

        assert result == "notification created"
        assert (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .count()
            == 1
        )
    finally:
        db.close()


def test_muting_quotes_does_not_also_mute_projects(client, workspace):
    """Categories are independent — the whole point of having more than
    one."""
    headers, tenant_id, user_id = workspace
    client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "quote_activity", "in_app": False, "email": False}]},
        headers=headers,
    )

    db = SessionLocal()
    try:
        _automation_notification(db, tenant_id, user_id, subject_type="quote")
        _automation_notification(db, tenant_id, user_id, subject_type="project")

        remaining = (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .all()
        )
        assert len(remaining) == 1
    finally:
        db.close()


# --- The three categories that were vocabulary until now -----------------
#
# A category that controls nothing is a mock with a table behind it. These
# prove each of the remaining three names a notification GeoCore really
# creates.


def test_a_task_an_automation_assigns_you_notifies_you(workspace):
    """Sprint 036's own settings card promised "when something an
    automation created is waiting on you" and nothing ever produced it.
    Now something does."""
    from app.automations import actions

    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        result = actions.perform(
            db,
            action={"type": "create_task", "config": {"title": "Chase the surveyor"}},
            tenant_id=tenant_id,
            subject={"id": str(uuid.uuid4()), "assigned_user_id": str(user_id)},
            dedupe_key=f"pytest-task-{uuid.uuid4().hex}",
            now=None,
            context={"subject_type": "project"},
        )
        assert result == "task created"

        notifications = (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .all()
        )
        assert len(notifications) == 1
        assert "Chase the surveyor" in notifications[0].message
    finally:
        db.close()


def test_a_muted_task_assignment_creates_the_task_but_not_the_notification(
    client, workspace
):
    """Muting a notification must never stop the work itself being
    created — the task is the record of what has to happen."""
    from app.automations import actions
    from app.database.models import Task

    headers, tenant_id, user_id = workspace
    client.put(
        "/api/v1/notifications/preferences",
        json={"preferences": [{"category": "task_assignment", "in_app": False, "email": False}]},
        headers=headers,
    )

    db = SessionLocal()
    try:
        result = actions.perform(
            db,
            action={"type": "create_task", "config": {"title": "Chase the surveyor"}},
            tenant_id=tenant_id,
            subject={"id": str(uuid.uuid4()), "assigned_user_id": str(user_id)},
            dedupe_key=f"pytest-task-{uuid.uuid4().hex}",
            now=None,
            context={"subject_type": "project"},
        )
        assert result == "task created"

        assert db.query(Task).filter(Task.tenant_id == tenant_id).count() == 1
        assert (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .count()
            == 0
        )
        db.execute(delete(Task).where(Task.tenant_id == tenant_id))
        db.commit()
    finally:
        db.close()


def test_a_failed_communication_notifies_the_workspace(workspace):
    """An email to a customer that bounced is exactly the thing a business
    needs told about — it means a quote is sitting unread."""
    from app.notifications import delivery_alerts

    _, tenant_id, user_id = workspace
    db = SessionLocal()
    try:
        communication = crud.create_communication(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            message_type="quote_sent",
            recipient="bounced@example.invalid",
            sender_identity="GeoCore <x@send.example>",
            subject="Your quote",
            body_html="<p>x</p>",
            body_text="x",
            dedupe_key=f"pytest-bounce-{uuid.uuid4().hex}",
            status="bounced",
        )

        delivery_alerts.notify_delivery_failure(db, communication)

        notifications = (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .all()
        )
        assert len(notifications) == 1
        assert "bounced@example.invalid" in notifications[0].message
    finally:
        db.close()


def test_a_muted_delivery_failure_creates_no_notification(client, workspace):
    from app.notifications import delivery_alerts

    headers, tenant_id, _ = workspace
    client.put(
        "/api/v1/notifications/preferences",
        json={
            "preferences": [
                {"category": "communication_failure", "in_app": False, "email": False}
            ]
        },
        headers=headers,
    )

    db = SessionLocal()
    try:
        communication = crud.create_communication(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            message_type="quote_sent",
            recipient="bounced@example.invalid",
            sender_identity="GeoCore <x@send.example>",
            subject="Your quote",
            body_html="<p>x</p>",
            body_text="x",
            dedupe_key=f"pytest-bounce-{uuid.uuid4().hex}",
            status="bounced",
        )

        delivery_alerts.notify_delivery_failure(db, communication)

        assert (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_a_successful_send_never_notifies_anyone(workspace):
    """Only failures are worth interrupting someone for."""
    from app.notifications import delivery_alerts

    _, tenant_id, _ = workspace
    db = SessionLocal()
    try:
        communication = crud.create_communication(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            message_type="quote_sent",
            recipient="fine@example.invalid",
            sender_identity="GeoCore <x@send.example>",
            subject="Your quote",
            body_html="<p>x</p>",
            body_text="x",
            dedupe_key=f"pytest-ok-{uuid.uuid4().hex}",
            status="sent",
        )

        delivery_alerts.notify_delivery_failure(db, communication)

        assert (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .count()
            == 0
        )
    finally:
        db.close()


def test_an_automation_failure_notifies_the_owner(workspace):
    """An automation that has quietly stopped working is the failure mode
    the whole feature defends against (Sprint 036's own words). Until now
    it was visible only to someone who went looking at run history."""
    from app.notifications import automation_alerts

    _, tenant_id, _ = workspace
    db = SessionLocal()
    try:
        automation_alerts.notify_automation_failure(
            db,
            tenant_id=tenant_id,
            automation_name="Chase expiring quotes",
            detail="quote not found",
            dedupe_key=f"pytest-autofail-{uuid.uuid4().hex}",
        )

        notifications = (
            db.query(NotificationRecord)
            .filter(NotificationRecord.tenant_id == tenant_id)
            .all()
        )
        assert len(notifications) == 1
        assert "Chase expiring quotes" in notifications[0].message
    finally:
        db.close()
