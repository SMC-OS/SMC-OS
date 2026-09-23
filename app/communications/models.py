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

from pydantic import BaseModel, ConfigDict


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
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
    QUOTE_SENT = "quote_sent"
    QUOTE_FOLLOW_UP = "quote_follow_up"
    PROJECT_CONFIRMATION = "project_confirmation"
    PROJECT_UPDATE = "project_update"
    PROJECT_COMPLETION = "project_completion"
    REVIEW_REQUEST = "review_request"
    # Phase B — no-card trial lifecycle and public demo requests.
    TRIAL_ENDING = "trial_ending"
    TRIAL_ENDED = "trial_ended"
    DEMO_REQUEST_SALES_NOTIFICATION = "demo_request_sales_notification"
    DEMO_REQUEST_CONFIRMATION = "demo_request_confirmation"


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
