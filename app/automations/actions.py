"""What an automation is allowed to do (Sprint 036, Workstream G; extended
Sprint 038, Phase 3).

Sprint 036 built four actions, **all internal to the workspace** — none
transmitted anything to a customer, because GeoCore had no outbound email
infrastructure at all. `draft_message` *prepared* a message and handed it
to a human as a task; a person read it and sent it themselves.

Sprint 038 adds the first genuinely customer-facing action,
`send_quote_follow_up`, now that real transactional email exists
(app/communications/). The internal/customer-facing line is still drawn
sharply — see `CUSTOMER_FACING_ACTION_TYPES` below — because a rule that
reaches a real customer's inbox deserves a different trust posture than
one that only ever creates a row in this tenant's own workspace.

Five actions:

  create_notification      — an in-app notification for the workspace.
  create_task              — an internal follow-up someone has to do.
  draft_message            — a prepared message for a human to review and
                             send. A task with a body, not a transmission.
  create_project_from_quote— delegates to the already-audited, already-
                             idempotent quote_service.handoff. Valid only
                             on quote.approved, because handoff refuses
                             anything that is not approved anyway.
  send_quote_follow_up     — customer-facing. Sends a real email via
                             DeliveryService using a fixed, reviewed
                             template — never rule-author free text.

Idempotency is per-action, not just per-run: each side effect carries its
own dedupe_key derived from the run's, so a run that fails at action 2 of
3 and is retried does not double-create action 1's task (or, now,
double-send action 3's email).
"""

import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.automations.subjects import render
from app.database import crud
from app.notifications import categories as notification_categories
from app.notifications import preferences
from app.notifications.models import NotificationType

#: The four classes of thing an automation can do, in the order a person
#: cares about them. The distinction that matters most is the third: does
#: this reach a real customer's inbox?
ACTION_KINDS: tuple[str, ...] = (
    "internal_notification",
    "internal_task",
    "customer_communication",
    "ai_draft",
)

#: What each action is, in the words the builder shows.
#:
#: Sprint 039 (Workstream E) moved this here from the frontend, where a
#: hardcoded label map had four entries for five action types — so Sprint
#: 038's `send_quote_follow_up` rendered with no label at all. A UI that
#: is *served* the catalogue cannot describe an action wrongly, because it
#: does not describe actions.
ACTION_CATALOGUE: dict[str, dict] = {
    "create_notification": {
        "label": "Send an in-app notification",
        "description": "Puts a notification in the bell menu for whoever the record is assigned to.",
        "kind": "internal_notification",
    },
    "create_task": {
        "label": "Create a follow-up task",
        "description": "Adds a task to your workspace and assigns it to someone.",
        "kind": "internal_task",
    },
    "draft_message": {
        "label": "Prepare a message for you to send",
        "description": (
            "Writes the message you specify into a task for someone to read "
            "and send themselves. Nothing is transmitted."
        ),
        "kind": "internal_task",
    },
    "draft_message_with_ai": {
        "label": "Ask GeoCore AI to draft a message",
        "description": (
            "GeoCore AI writes a draft from this record and leaves it in a "
            "task for a person to review, edit and send. It never sends "
            "anything itself."
        ),
        "kind": "ai_draft",
    },
    "create_project_from_quote": {
        "label": "Turn the quote into a project",
        "description": "Creates the job from an approved quote, carrying its details over.",
        "kind": "internal_task",
    },
    "send_quote_follow_up": {
        "label": "Email the customer a quote follow-up",
        "description": (
            "Sends a real email to your customer, using GeoCore's reviewed "
            "follow-up template."
        ),
        "kind": "customer_communication",
    },
}

ACTION_TYPES = frozenset(ACTION_CATALOGUE)

# The builder UI's own distinction (Sprint 038 brief §9): these reach a
# real customer inbox and deserve stronger confirmation than an internal
# action.
#
# Sprint 039 derives it from the catalogue rather than maintaining a
# second list beside it — two sources of the same truth eventually
# disagree, and the direction this one would fail in is "sends email
# nobody expected".
CUSTOMER_FACING_ACTION_TYPES = frozenset(
    key
    for key, entry in ACTION_CATALOGUE.items()
    if entry["kind"] == "customer_communication"
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
    """An in-app notification for the workspace.

    Sprint 039 (Workstream B) routes this through
    `preferences.notify()` rather than straight to
    `crud.create_notification`. A recipient who has muted this category
    gets no row at all — not a hidden one — and the run says so, which is
    the difference between "the automation did nothing" and "the
    automation did what this person asked for".
    """
    title = render(config.get("title") or "Automation", subject)
    message = render(config.get("message") or "", subject)

    if crud.get_notification_by_dedupe_key(db, dedupe_key) is not None:
        return "notification already existed"

    recipient_id = _resolve_recipient(db, tenant_id, subject)
    category = notification_categories.for_subject_type(context["subject_type"])

    created = preferences.notify(
        db,
        tenant_id=tenant_id,
        recipient_user_id=recipient_id,
        category=category,
        title=title,
        message=message,
        dedupe_key=dedupe_key,
        notification_type=NotificationType.INFO.value,
        source_type=context["subject_type"],
        source_id=_subject_uuid(subject),
        now=now,
    )
    if created is None:
        # Either the recipient muted this category, or a concurrent
        # dispatch won the dedupe race. Both are "nothing to do", and
        # neither is a failure — see preferences.notify()'s docstring.
        if recipient_id is not None and not preferences.allows(
            db, tenant_id, recipient_id, category, notification_categories.IN_APP
        ):
            return "skipped: the recipient has muted this notification preference"
        return "notification already existed"

    _maybe_email_copy(
        db,
        tenant_id=tenant_id,
        recipient_user_id=recipient_id,
        category=category,
        title=title,
        message=message,
        dedupe_key=dedupe_key,
    )
    return "notification created"


def _run_create_task(db, *, tenant_id, subject, config, dedupe_key, now, context, body=None):
    title = render(config.get("title") or "Follow up", subject)
    task_body = render(config.get("body") or body or "", subject) or None

    if crud.get_task_by_dedupe_key(db, dedupe_key) is not None:
        return "task already existed"

    assignee_id = _resolve_recipient(db, tenant_id, subject)

    try:
        crud.create_task(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            title=title[:200],
            body=task_body,
            due_at=_due_at(config, now),
            assigned_user_id=assignee_id,
            source_type=context["subject_type"],
            source_id=_subject_uuid(subject),
            dedupe_key=dedupe_key,
        )
    except IntegrityError:
        db.rollback()
        return "task already existed"

    # Sprint 039 (Workstream B) — tell the person whose name is on it.
    # Sprint 036's settings card already promised "when something an
    # automation created is waiting on you" and nothing produced it.
    #
    # Deliberately after the task is committed, and deliberately not
    # allowed to change this action's result: muting the notification must
    # never stop the *work* being recorded, because the task is the record
    # of what has to happen.
    _notify_assignee(
        db,
        tenant_id=tenant_id,
        assignee_id=assignee_id,
        task_title=title,
        dedupe_key=dedupe_key,
        source_type=context["subject_type"],
        source_id=_subject_uuid(subject),
    )
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


def _run_send_quote_follow_up(db, *, tenant_id, subject, config, dedupe_key, now, context):
    """Email the customer a follow-up on a quote nearing expiry, still
    unanswered — Sprint 038's first genuinely customer-facing action.
    Distinct on purpose from draft_message (which stays purely internal,
    §9 above): this reaches the customer's own inbox, through
    DeliveryService, using the same reviewed template "Send quote" uses.
    `config` carries no free-text fields — unlike the internal actions,
    what a customer receives is not something a rule author gets to type;
    only the template does.

    Delivery failure/suppression/no-provider-configured never raises
    ActionError — DeliveryService.send() already returns a truthful
    Communication row for every one of those; this action's own job ends
    once that row exists. A stuck-forever automation because the mailbox
    is unreachable would be a worse failure than an honestly-recorded
    failed send."""
    # Imported here for the same reason _run_create_project_from_quote's
    # quote-service import is: keeps this the only place in the
    # automations package that needs app.communications/app.portal, no
    # cycle risk at module-import time.
    from app.communications.models import CommunicationType
    from app.communications.service import delivery_service
    from app.communications.templates import render_quote_follow_up
    from app.core.config import settings
    from app.portal.service import portal_service

    quote_id = _subject_uuid(subject)
    if quote_id is None:
        raise ActionError("send_quote_follow_up needs a quote subject")

    quote = crud.get_quote_by_id(db, quote_id, tenant_id)
    if quote is None:
        raise ActionError("quote not found")
    if quote.status != "sent":
        # The scan that dispatches this only selects "sent" quotes, but a
        # delayed/retried run can land after the customer has since
        # approved or the quote was otherwise taken off the table —
        # re-check against the live row rather than trust the subject
        # snapshot the scan took.
        return "skipped: quote is no longer awaiting a response"
    if quote.customer_id is None:
        return "skipped: quote has no linked customer"

    customer = crud.get_customer_by_id(db, quote.customer_id, tenant_id)
    if customer is None or not customer.email:
        return "skipped: customer has no email on file"

    tenant = crud.get_tenant_by_id(db, tenant_id)
    owner_id = _resolve_recipient(db, tenant_id, {})
    if owner_id is None:
        raise ActionError("no active Owner to attribute the portal link to")

    # A fresh portal link every time, deliberately: a link's raw token is
    # only ever returned once, at creation (same convention as
    # Invitation), so an existing link's token cannot be recovered to
    # reuse. Links are not single-use, so this does not invalidate any
    # link already shared with this customer some other way.
    _portal_link, raw_token = portal_service.create_link(
        db, tenant_id=tenant_id, created_by_user_id=owner_id, customer_id=customer.id
    )
    portal_url = f"{settings.frontend_base_url}/portal/{raw_token}"

    rendered = render_quote_follow_up(
        tenant_display_name=tenant.name if tenant is not None else "",
        customer_name=customer.name,
        quote_title=quote.title or "your quote",
        portal_url=portal_url,
    )
    communication = delivery_service.send(
        db,
        tenant=tenant,
        message_type=CommunicationType.QUOTE_FOLLOW_UP,
        recipient=customer.email,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        # The engine's own dedupe_key (per-action, derived from the run's
        # discriminator — see this module's docstring) is reused as-is
        # here, so a single quote can never receive two automated
        # follow-up emails for the same expiry window even under a
        # concurrent/retried worker — the same guarantee dedupe_key
        # already gives every other action, now extended to a real send.
        dedupe_key=dedupe_key,
        customer_id=customer.id,
        quote_id=quote.id,
    )
    return f"follow-up email {communication.status}"


def _run_draft_message_with_ai(db, *, tenant_id, subject, config, dedupe_key, now, context):
    """Have GeoCore AI draft a message, and leave it for a person to send.

    The AI-draft counterpart to `draft_message`: same destination (a task
    a human reads), different author. It is emphatically **not** a send —
    `app/ai/drafting.py` has no delivery import and its result shape has
    no delivery field, so an automation cannot become a way for a model
    to reach a customer unreviewed.

    Every failure mode resolves to a skip with a reason rather than an
    ActionError: no AI provider connected, no customer on the record, a
    model that would not answer. An automation that is stuck failing
    because the mailbox of a language model is unreachable is a worse
    outcome than one that honestly records why it did nothing.
    """
    from app.ai.drafting import (
        DRAFT_KINDS,
        DraftRequest,
        DraftingUnavailableError,
        EntityNotFoundError,
        ai_drafting_service,
    )

    kind = config.get("kind") or "general"
    if kind not in DRAFT_KINDS:
        raise ActionError(f"draft kind must be one of {sorted(DRAFT_KINDS)}")

    subject_type = context["subject_type"]
    customer_raw = subject.get("customer_id") if subject_type != "customer" else subject.get("id")
    if not customer_raw:
        return "skipped: nothing to draft to — this record has no customer"

    try:
        request = DraftRequest(
            kind=kind,
            customer_id=uuid.UUID(customer_raw),
            quote_id=_subject_uuid(subject) if subject_type == "quote" else None,
            project_id=_subject_uuid(subject) if subject_type == "project" else None,
        )
    except ValueError as exc:
        raise ActionError(str(exc))

    try:
        draft = ai_drafting_service.draft(db, tenant_id=tenant_id, request=request)
    except DraftingUnavailableError:
        return "skipped: no AI provider is connected to this workspace"
    except EntityNotFoundError:
        return "skipped: the record this would be about no longer exists"

    return _run_create_task(
        db,
        tenant_id=tenant_id,
        subject=subject,
        config={
            "title": f"Review and send: {draft.subject}",
            "body": draft.body,
            **{k: v for k, v in config.items() if k == "due_in_days"},
        },
        dedupe_key=dedupe_key,
        now=now,
        context=context,
    )


_HANDLERS = {
    "create_notification": _run_create_notification,
    "create_task": _run_create_task,
    "draft_message": _run_draft_message,
    "create_project_from_quote": _run_create_project_from_quote,
    "send_quote_follow_up": _run_send_quote_follow_up,
    "draft_message_with_ai": _run_draft_message_with_ai,
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


def _maybe_email_copy(db, *, tenant_id, recipient_user_id, category, title, message, dedupe_key):
    """Email the recipient a copy, if they asked for one (Sprint 039).

    Off by default for every category, so this is a no-op for everyone who
    has not deliberately opted in. Never raises: a failure here must not
    turn a successful automation run into a failed one, and
    DeliveryService already records every outcome truthfully.
    """
    if recipient_user_id is None:
        return
    try:
        preferences.send_email_copy(
            db,
            tenant_id=tenant_id,
            recipient_user_id=recipient_user_id,
            category=category,
            headline=title,
            detail=message,
            dedupe_key=dedupe_key,
        )
    except Exception:  # noqa: BLE001 — an email copy is never load-bearing
        db.rollback()


def _notify_assignee(db, *, tenant_id, assignee_id, task_title, dedupe_key, source_type, source_id):
    """Tell whoever a new automated task was assigned to.

    Never raises and never changes the caller's result — see the comment
    at its call site for why the task must survive a muted or failed
    notification.
    """
    if assignee_id is None:
        return
    try:
        created = preferences.notify(
            db,
            tenant_id=tenant_id,
            recipient_user_id=assignee_id,
            category="task_assignment",
            title="A task is waiting for you",
            message=task_title,
            dedupe_key=f"task_assigned:{dedupe_key}",
            notification_type=NotificationType.INFO.value,
            source_type=source_type,
            source_id=source_id,
        )
        if created is not None:
            preferences.send_email_copy(
                db,
                tenant_id=tenant_id,
                recipient_user_id=assignee_id,
                category="task_assignment",
                headline="A task is waiting for you",
                detail=task_title,
                dedupe_key=f"task_assigned:{dedupe_key}",
            )
    except Exception:  # noqa: BLE001 — a notification is never load-bearing
        db.rollback()
