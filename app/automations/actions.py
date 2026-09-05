"""What an automation is allowed to do (Sprint 036, Workstream G).

**Every action in this module is internal to the workspace. None of them
transmits anything to a customer.** GeoCore has no outbound email, SMS or
messaging infrastructure — that was verified across the whole repository
during Sprint 036 discovery — so an action that claimed to "email the
customer a review request" would be a lie in the product. Instead, the
`draft_message` action *prepares* the message and hands it to a human as a
task; a person reads it and sends it themselves.

Four actions:

  create_notification      — an in-app notification for the workspace.
  create_task              — an internal follow-up someone has to do.
  draft_message            — a prepared message for a human to review and
                             send. A task with a body, not a transmission.
  create_project_from_quote— delegates to the already-audited, already-
                             idempotent quote_service.handoff. Valid only
                             on quote.approved, because handoff refuses
                             anything that is not approved anyway.

Idempotency is per-action, not just per-run: each side effect carries its
own dedupe_key derived from the run's, so a run that fails at action 2 of
3 and is retried does not double-create action 1's task.
"""

import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.automations.subjects import render
from app.database import crud
from app.notifications.models import NotificationType

ACTION_TYPES = frozenset(
    {"create_notification", "create_task", "draft_message", "create_project_from_quote"}
)

# A due date offset has to be bounded: an automation with due_in_days of
# 100000 produces a task nobody will ever see, and one with a negative
# value produces a task that is already overdue the moment it is made.
MAX_DUE_IN_DAYS = 365


class ActionError(Exception):
    """A single action could not be performed. Caught by the engine, which
    records the run as failed with this message and moves on — an
    automation failure must never break the user action that triggered
    it."""


def _resolve_recipient(db: Session, tenant_id: uuid.UUID, subject: dict) -> uuid.UUID | None:
    """Who a notification or task belongs to.

    Exactly the Sprint 024 rule, reused rather than reinvented: the
    subject's assigned user if it has one and they belong to this tenant,
    otherwise the tenant's earliest-created Owner, otherwise nobody (in
    which case the notification is a tenant-wide broadcast and the task is
    unassigned — never silently dropped).
    """
    assigned = subject.get("assigned_user_id")
    if assigned:
        try:
            user = crud.get_user_by_id(db, uuid.UUID(assigned))
        except ValueError:
            user = None
        if user is not None and user.tenant_id == tenant_id:
            return user.id

    owners = [
        user
        for user in crud.list_users_by_tenant(db, tenant_id)
        if user.role == UserRole.OWNER.value and user.is_active
    ]
    return owners[0].id if owners else None


def _due_at(config: dict, now):
    raw = config.get("due_in_days")
    if raw is None:
        return None
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise ActionError("due_in_days must be a whole number of days")
    if not 0 <= days <= MAX_DUE_IN_DAYS:
        raise ActionError(f"due_in_days must be between 0 and {MAX_DUE_IN_DAYS}")
    return now + timedelta(days=days)


def _subject_uuid(subject: dict) -> uuid.UUID | None:
    raw = subject.get("id")
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


def _run_create_notification(db, *, tenant_id, subject, config, dedupe_key, now, context):
    title = render(config.get("title") or "Automation", subject)
    message = render(config.get("message") or "", subject)

    if crud.get_notification_by_dedupe_key(db, dedupe_key) is not None:
        return "notification already existed"

    try:
        crud.create_notification(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title[:200],
            message=message[:500],
            type=NotificationType.INFO.value,
            timestamp=now,
            read=False,
            recipient_user_id=_resolve_recipient(db, tenant_id, subject),
            source_type=context["subject_type"],
            source_id=_subject_uuid(subject),
            dedupe_key=dedupe_key,
        )
    except IntegrityError:
        # A concurrent dispatch won the race to the same dedupe_key. The
        # UNIQUE constraint is the hard backstop the pre-check above is
        # defending in depth, not replacing (Sprint 024's precedent). Roll
        # back so this session stays usable for the next action.
        db.rollback()
        return "notification already existed"
    return "notification created"


def _run_create_task(db, *, tenant_id, subject, config, dedupe_key, now, context, body=None):
    title = render(config.get("title") or "Follow up", subject)
    task_body = render(config.get("body") or body or "", subject) or None

    if crud.get_task_by_dedupe_key(db, dedupe_key) is not None:
        return "task already existed"

    try:
        crud.create_task(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title[:200],
            body=task_body,
            due_at=_due_at(config, now),
            assigned_user_id=_resolve_recipient(db, tenant_id, subject),
            source_type=context["subject_type"],
            source_id=_subject_uuid(subject),
            dedupe_key=dedupe_key,
        )
    except IntegrityError:
        db.rollback()
        return "task already existed"
    return "task created"


def _run_draft_message(db, *, tenant_id, subject, config, dedupe_key, now, context):
    """Prepare a message for a human to review and send.

    This creates a task carrying the drafted text. It does not send
    anything, and the task title says so, because GeoCore has no channel
    to send it through. When outbound delivery is genuinely built, this
    action gains a "send" counterpart — it does not quietly start
    transmitting.
    """
    default_title = "Message ready to send to {customer_name}"
    config = {
        **config,
        "title": config.get("title") or default_title,
        "body": config.get("body") or config.get("message") or "",
    }
    result = _run_create_task(db, tenant_id=tenant_id, subject=subject, config=config,
                              dedupe_key=dedupe_key, now=now, context=context)
    return "message drafted" if result == "task created" else result


def _run_create_project_from_quote(db, *, tenant_id, subject, config, dedupe_key, now, context):
    # Imported here rather than at module scope: app.quotes.service imports
    # the automation dispatcher, and a top-level import in both directions
    # is a cycle. This action is the only place in the automation package
    # that needs the quote service.
    from app.quotes.service import (
        QuoteApprovalStateError,
        QuoteNotFoundError,
        quote_service,
    )

    quote_id = _subject_uuid(subject)
    if quote_id is None:
        raise ActionError("create_project_from_quote needs a quote subject")

    try:
        # handoff() is idempotent by design (Sprint 020): it returns the
        # existing project when one already exists for this quote, and the
        # DB carries a UNIQUE on projects.quote_id behind that. So this
        # action needs no dedupe logic of its own — re-running it cannot
        # create a second project.
        project = quote_service.handoff(db, quote_id, tenant_id)
    except QuoteNotFoundError:
        raise ActionError("quote not found")
    except QuoteApprovalStateError as exc:
        raise ActionError(f"quote is not approved (status: {exc})")
    return f"project {project.id} ready"


_HANDLERS = {
    "create_notification": _run_create_notification,
    "create_task": _run_create_task,
    "draft_message": _run_draft_message,
    "create_project_from_quote": _run_create_project_from_quote,
}


def perform(
    db: Session,
    *,
    action: dict,
    tenant_id: uuid.UUID,
    subject: dict,
    dedupe_key: str,
    now,
    context: dict,
) -> str:
    action_type = action.get("type")
    handler = _HANDLERS.get(action_type)
    if handler is None:
        raise ActionError(f"unknown action type: {action_type!r}")

    return handler(
        db,
        tenant_id=tenant_id,
        subject=subject,
        config=action.get("config") or {},
        dedupe_key=dedupe_key,
        now=now,
        context=context,
    )
