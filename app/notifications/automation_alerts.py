"""Telling the workspace when one of its automations failed to run
(Sprint 039, Workstream B).

Sprint 036 built `AutomationRun` precisely because "an automation that
quietly stopped working is the failure mode this feature has to defend
against" — and then made that failure visible only to someone who went
looking at the run history panel. Nobody goes looking at a run history
panel to discover a problem they do not know they have.

This closes that loop: an automation that fails tells the Owner once, in
the bell menu they already watch, and never again for the same failure.
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.database import crud
from app.notifications import preferences
from app.notifications.models import NotificationType

CATEGORY = "automation_outcome"


def _owner_id(db: Session, tenant_id: uuid.UUID) -> uuid.UUID | None:
    owners = [
        user
        for user in crud.list_users_by_tenant(db, tenant_id)
        if user.role == UserRole.OWNER.value and user.is_active
    ]
    return owners[0].id if owners else None


def notify_automation_failure(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    automation_name: str,
    detail: str,
    dedupe_key: str,
    automation_id: uuid.UUID | None = None,
) -> None:
    """Record (and optionally email) one automation-failure notification.

    `dedupe_key` is the caller's job, and the engine derives it from the
    automation and the failure so a rule failing on every dispatch does
    not produce a notification per dispatch. An automation broken for a
    week should be one unread item, not four hundred.

    Never raises. An automation failure must not be made worse by a
    failure to report it, and the engine's own invariant is that nothing
    in this path may break the user action that triggered the run.
    """
    recipient_id = _owner_id(db, tenant_id)
    if recipient_id is None:
        return

    headline = "An automation didn't run"
    message = f"{automation_name} failed: {detail}"

    try:
        created = preferences.notify(
            db,
            tenant_id=tenant_id,
            recipient_user_id=recipient_id,
            category=CATEGORY,
            title=headline,
            message=message,
            dedupe_key=dedupe_key,
            notification_type=NotificationType.WARNING.value,
            source_type="automation",
            source_id=automation_id,
        )
        if created is not None:
            preferences.send_email_copy(
                db,
                tenant_id=tenant_id,
                recipient_user_id=recipient_id,
                category=CATEGORY,
                headline=headline,
                detail=message,
                dedupe_key=dedupe_key,
            )
    except Exception:  # noqa: BLE001 — reporting a failure must not fail
        db.rollback()
