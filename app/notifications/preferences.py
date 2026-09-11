"""Reading, storing and *enforcing* notification preferences (Sprint 039,
Workstream B).

The important word is enforcing. Sprint 036's version of this feature
stored four flags in the browser and filtered what the notifications panel
rendered. That is not a preference, it is a display filter: the rows were
still created, the unread count still counted them, and any second client
— a phone, a future digest email — would have shown every one of them.

Here, a muted notification **is never created at all**. `notify()` is the
single write path automated notifications go through, and it decides
before `crud.create_notification` is ever called.

Three rules, each of which is a test in
tests/test_notification_preferences.py:

1. **Defaults preserve today's behaviour.** No stored row means in-app on,
   email off. A user who never opens Settings sees exactly what they saw
   before this sprint, and nobody starts receiving email they did not ask
   for.

2. **A broadcast is never filtered.** A notification with no
   `recipient_user_id` is addressed to the whole workspace, so there is no
   one whose preference could apply. Muting every category must not
   silence a tenant-wide notice.

3. **Unknown categories fail open.** A notification whose category this
   build does not recognise is delivered. Swallowing it would be a silent
   failure, and silence is the one thing a notification system must not
   produce by accident.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import NotificationRecord
from app.notifications import categories
from app.notifications.models import NotificationType


def resolve(db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, dict]:
    """Every category and this user's effective setting for it.

    Always complete — one entry per category, stored or defaulted — so the
    settings screen never has to know which rows happen to exist.
    """
    stored = {
        row.category: row
        for row in crud.list_notification_preferences(db, tenant_id, user_id)
    }
    resolved: dict[str, dict] = {}
    for category in categories.CATEGORIES:
        row = stored.get(category.key)
        resolved[category.key] = {
            "in_app": row.in_app if row is not None else category.default_in_app,
            "email": row.email if row is not None else category.default_email,
        }
    return resolved


def allows(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    category_key: str | None,
    channel: str,
) -> bool:
    """Whether this user wants `category_key` on `channel`.

    Rule 3 above: an unrecognised category is allowed on the in-app
    channel rather than dropped.
    """
    if category_key is None or category_key not in categories.CATEGORY_KEYS:
        return categories.default_for(category_key or "", channel)

    row = crud.get_notification_preference(db, tenant_id, user_id, category_key)
    if row is None:
        return categories.default_for(category_key, channel)
    return row.in_app if channel == categories.IN_APP else row.email


def replace(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    updates: list[dict],
) -> dict[str, dict]:
    """Store a user's choices.

    A partial update: only the categories named are written, so a client
    that knows about four categories cannot reset the two it has not heard
    of. Every write is an upsert on (user_id, category), which the table's
    UNIQUE constraint enforces underneath.
    """
    for update in updates:
        crud.upsert_notification_preference(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            category=update["category"],
            in_app=update["in_app"],
            email=update["email"],
            commit=False,
        )
    db.commit()
    return resolve(db, tenant_id, user_id)


def notify(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    recipient_user_id: uuid.UUID | None,
    category: str | None,
    title: str,
    message: str,
    dedupe_key: str | None = None,
    notification_type: str = NotificationType.INFO.value,
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    now=None,
) -> NotificationRecord | None:
    """Create a notification, unless its recipient has asked not to get it.

    Returns the created row, or `None` when the recipient has this
    category muted on the in-app channel — the caller can then report
    "suppressed by preference" rather than pretending it sent something.

    The email channel is handled by `send_email_copy` below rather than
    here, so a mailer outage can never stop an in-app notification being
    recorded.
    """
    from datetime import datetime, timezone

    if recipient_user_id is not None and not allows(
        db, tenant_id, recipient_user_id, category, categories.IN_APP
    ):
        return None

    if dedupe_key is not None and crud.get_notification_by_dedupe_key(db, dedupe_key) is not None:
        return None

    try:
        return crud.create_notification(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title[:200],
            message=message[:500],
            type=notification_type,
            timestamp=now or datetime.now(timezone.utc),
            read=False,
            recipient_user_id=recipient_user_id,
            source_type=source_type,
            source_id=source_id,
            dedupe_key=dedupe_key,
        )
    except IntegrityError:
        # A concurrent writer won the race to the same dedupe_key. The
        # UNIQUE constraint is the hard backstop the pre-check above is
        # defending in depth, not replacing (Sprint 024's precedent). Roll
        # back so this session stays usable.
        db.rollback()
        return None


def wants_email(
    db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID | None, category: str | None
) -> bool:
    """Whether a copy of this notification should also be emailed.

    Separate from `notify()` on purpose: the in-app record is the thing
    that must always be written, and an email is an extra. A caller sends
    the copy only after the record exists.
    """
    if user_id is None:
        # A broadcast has no addressee, so nobody has opted in to an email
        # copy of it. Mailing the whole workspace because a notice had no
        # recipient would be precisely the wrong reading of rule 2.
        return False
    return allows(db, tenant_id, user_id, category, categories.EMAIL)


def send_email_copy(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    recipient_user_id: uuid.UUID | None,
    category: str | None,
    headline: str,
    detail: str,
    dedupe_key: str,
) -> None:
    """Email a colleague a copy of a notification they opted in to.

    Deliberately fire-and-forget from the caller's point of view, and
    deliberately *after* the in-app record exists: the record is the thing
    that must always be written, and a mail provider having a bad morning
    must never cost someone their notification. `DeliveryService.send()`
    already returns a truthful row for every outcome and never raises past
    its own boundary, so this cannot break the automation that triggered
    it either.

    Imported inside the function for the same reason
    app/automations/actions.py imports the quote service inside its
    handler: app.communications imports nothing from app.notifications
    today, and a module-level import in both directions would be a cycle
    waiting to happen.
    """
    if not wants_email(db, tenant_id, recipient_user_id, category):
        return

    from app.communications.models import CommunicationType
    from app.communications.service import delivery_service
    from app.communications.templates import render_workspace_alert

    user = crud.get_user_by_id(db, recipient_user_id)
    if user is None or not user.email or not user.is_active:
        return

    tenant = crud.get_tenant_by_id(db, tenant_id)
    rendered = render_workspace_alert(
        tenant_display_name=tenant.name if tenant is not None else "",
        recipient_name=user.name or user.email,
        headline=headline,
        detail=detail,
    )
    delivery_service.send(
        db,
        tenant=tenant,
        message_type=CommunicationType.WORKSPACE_ALERT,
        recipient=user.email,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        # Derived from the notification's own dedupe key, so the same
        # notification can never be emailed twice however many times its
        # automation is retried — the same guarantee every other action
        # already has, extended to this copy.
        dedupe_key=f"notification_email:{dedupe_key}",
    )
