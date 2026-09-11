"""Telling the workspace when an email to a customer did not arrive
(Sprint 039, Workstream B).

Sprint 038 recorded delivery failures faithfully and told nobody. A quote
that bounced looks exactly like a quote the customer is thinking about,
and the difference matters enormously to whoever is waiting on the answer.

Only genuine failures notify. A `sent` or `delivered` row is the system
working, and interrupting someone to say so would train them to ignore
the bell. `suppressed` also stays quiet: it means the address was already
known bad, which the bounce that put it on the list already reported.
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.database import crud
from app.database.models import Communication
from app.notifications import preferences
from app.notifications.models import NotificationType

CATEGORY = "communication_failure"

#: The states worth telling a human about. `failed` with an `unavailable`
#: category is included deliberately — "no email provider is connected"
#: is precisely the sort of quiet misconfiguration a business should not
#: discover weeks later.
_FAILURE_STATUSES = frozenset({"failed", "bounced"})


def _owner_id(db: Session, tenant_id: uuid.UUID) -> uuid.UUID | None:
    """Who hears about a delivery failure.

    The tenant's earliest-created active Owner — the same
    resolve-a-recipient rule Sprint 024 established and
    app/automations/actions.py reuses. A delivery failure belongs to the
    business rather than to whoever happened to trigger the send, and the
    Owner is the one person guaranteed to exist.
    """
    owners = [
        user
        for user in crud.list_users_by_tenant(db, tenant_id)
        if user.role == UserRole.OWNER.value and user.is_active
    ]
    return owners[0].id if owners else None


def notify_delivery_failure(db: Session, communication: Communication) -> None:
    """Record (and optionally email) a notification about a failed send.

    Never raises: this runs from the send path and from the webhook
    handler, and neither may be broken by a notification. Idempotent
    through a dedupe key derived from the communication's own id, so a
    retried send or a replayed webhook cannot produce a second one.
    """
    if communication is None or communication.status not in _FAILURE_STATUSES:
        return

    recipient_id = _owner_id(db, communication.tenant_id)
    if recipient_id is None:
        return

    headline = (
        "An email to your customer bounced"
        if communication.status == "bounced"
        else "An email to your customer couldn't be sent"
    )
    detail = (
        f"{communication.subject} to {communication.recipient} — "
        f"{communication.failure_detail or 'no further detail from the mail provider'}"
    )
    dedupe_key = f"communication_failure:{communication.id}:{communication.status}"

    try:
        created = preferences.notify(
            db,
            tenant_id=communication.tenant_id,
            recipient_user_id=recipient_id,
            category=CATEGORY,
            title=headline,
            message=detail,
            dedupe_key=dedupe_key,
            notification_type=NotificationType.ERROR.value,
            source_type="communication",
            source_id=communication.id,
        )
        if created is not None:
            preferences.send_email_copy(
                db,
                tenant_id=communication.tenant_id,
                recipient_user_id=recipient_id,
                category=CATEGORY,
                headline=headline,
                detail=detail,
                dedupe_key=dedupe_key,
            )
    except Exception:  # noqa: BLE001 — a notification is never load-bearing
        db.rollback()
