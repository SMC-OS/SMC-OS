"""Pydantic schemas for the Sprint 038 communications ledger.

The ORM row (`app.database.models.Communication`) is the source of truth;
everything here is the API/service boundary shape around it. See
docs/SPRINTS/sprint-038.md §5 for the design rationale, and that same
doc's note on why this is `Communication`, not `Message` — that name and
table already belong to Sprint 017's portal chat feature
(app/database/models.py's `Message`, app/messages/).
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommunicationStatus(str, Enum):
    """Only states a real provider can actually establish (contract:
    docs/SPRINTS/sprint-038.md §3.4). `DELIVERED` is set only from a
    verified provider webhook event (Phase 2) — never assumed from the
    send API accepting the request, which only ever produces `SENT`.
    """

    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    SUPPRESSED = "suppressed"


class CommunicationType(str, Enum):
    """What kind of outbound message this is. Named `CommunicationType`
    rather than `MessageType` to keep clear distance from
    app/messages.models's unrelated portal-chat `MessageCreate`/`MessageOut`.
    """

    INVITATION = "invitation"
    QUOTE_SENT = "quote_sent"
    QUOTE_FOLLOW_UP = "quote_follow_up"
    PROJECT_CONFIRMATION = "project_confirmation"
    PROJECT_UPDATE = "project_update"
    PROJECT_COMPLETION = "project_completion"
    REVIEW_REQUEST = "review_request"
    # Sprint 039 (Workstream B) — the first message type addressed to a
    # colleague rather than a customer: an email copy of an in-app
    # notification, sent only to someone who explicitly opted in.
    WORKSPACE_ALERT = "workspace_alert"
    # Sprint 039 (Workstream C) — kinds a person can send after reviewing
    # an AI draft. Named for what the customer receives, so communication
    # history reads as a record of the conversation rather than of which
    # feature produced it.
    APPOINTMENT_UPDATE = "appointment_update"
    PAYMENT_REMINDER = "payment_reminder"
    CUSTOMER_MESSAGE = "customer_message"


class FailureCategory(str, Enum):
    """Drives whether the Phase 3 delivery-retry worker retries or gives
    up, and what the UI tells a user. `UNAVAILABLE` (no provider
    configured, or a suppressed recipient short-circuited before any
    provider call) is deliberately distinct from `TRANSIENT`/`PERMANENT`
    — a worker should never busy-retry a send that was never actually
    attempted against the provider."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    SUPPRESSED = "suppressed"
    UNAVAILABLE = "unavailable"


class CommunicationOut(BaseModel):
    """The safe, user-facing shape of one communication row — used by
    every history endpoint (customer/quote/project/invitation timelines).
    Deliberately excludes body_html/body_text (the full rendered content
    isn't needed for a timeline view and keeps API responses small;
    a future "view full message" endpoint can add a body-included variant
    if a real product need shows up) and never includes provider request/
    response internals — failure_detail is pre-sanitized at write time,
    never a raw provider error/stack trace.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID | None
    quote_id: uuid.UUID | None
    project_id: uuid.UUID | None
    invitation_id: uuid.UUID | None
    automation_id: uuid.UUID | None
    automation_run_id: uuid.UUID | None
    channel: str
    direction: str
    message_type: str
    recipient: str
    subject: str
    status: str
    attempt_count: int
    last_attempted_at: datetime | None
    failure_category: str | None
    failure_detail: str | None
    # Sprint 039 (§4 Decision 1). Derived, never stored: a spam complaint
    # proves the message *reached* the inbox, so overwriting `status` with
    # it would destroy the one fact this row exists to record. Sprint 038
    # records the complaint as an EmailSuppression pointing back here, and
    # this flag reads that relationship — leaving Sprint 038's
    # production-verified webhook handler untouched.
    complained: bool = False
    # Sprint 039 — whether the user-facing retry action applies. Served
    # rather than re-derived client-side, the same reason
    # /automations/meta and /projects/meta/pipeline are: a UI must never
    # offer an action the service will refuse.
    retryable: bool = False
    created_at: datetime
    updated_at: datetime


class EmailSuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    reason: str
    source_communication_id: uuid.UUID | None
    created_at: datetime


#: Which `CommunicationType` each drafting kind becomes once a human sends
#: it (app/ai/drafting.py's DRAFT_KINDS). A closed map, so a sender cannot
#: choose an arbitrary message type — history stays meaningful.
DRAFT_KIND_TO_MESSAGE_TYPE: dict[str, CommunicationType] = {
    "quote_delivery": CommunicationType.QUOTE_SENT,
    "quote_follow_up": CommunicationType.QUOTE_FOLLOW_UP,
    "project_update": CommunicationType.PROJECT_UPDATE,
    "appointment_update": CommunicationType.APPOINTMENT_UPDATE,
    "payment_reminder": CommunicationType.PAYMENT_REMINDER,
    "general": CommunicationType.CUSTOMER_MESSAGE,
}


class CustomerMessageRequest(BaseModel):
    """A message a person has read and decided to send (Sprint 039).

    **There is no recipient field, and that is the security property.**
    The address is always resolved from a `Customer` row the caller's own
    tenant owns, so this endpoint cannot be used to mail an arbitrary
    address — which is what stops it being a general-purpose mailer
    wearing a CRM's clothes.

    `idempotency_key` is generated by the client when the compose panel
    opens and reused if Send is pressed twice, so a double click resolves
    to the same communication instead of sending two emails. Absent, the
    server generates one — a deliberate send with no key is still a
    deliberate send, and refusing it would be worse than the small risk of
    a double-click.
    """

    customer_id: uuid.UUID
    kind: str
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)
    quote_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in DRAFT_KIND_TO_MESSAGE_TYPE:
            raise ValueError(
                f"kind must be one of {sorted(DRAFT_KIND_TO_MESSAGE_TYPE)}"
            )
        return value
