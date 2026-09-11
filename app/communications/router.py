"""Communication history + webhook API (Sprint 038).

No router-level `dependencies=[...]` (unlike app/tasks) — this router
mixes an authenticated history read with a fully public webhook, the same
shape app/invitations/router.py and app/billing/router.py's own docstrings
already establish for a router that genuinely needs both. Auth is applied
per-route below.

Every write path other than the webhook goes through
app/communications/service.py's DeliveryService, called from the module
that owns the trigger (app/invitations, app/quotes, app/automations),
never through a route here.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.communications.models import (
    DRAFT_KIND_TO_MESSAGE_TYPE,
    CommunicationOut,
    CustomerMessageRequest,
)
from app.communications.templates import render_customer_message
from app.communications.service import (
    CommunicationNotFoundError,
    CommunicationNotRetryableError,
    delivery_service,
)
from app.communications.webhooks import WebhookSignatureError, verify_svix_signature
from app.core.config import settings
from app.database import crud
from app.database.database import get_db
from app.database.models import User

router = APIRouter(prefix="/communications", tags=["communications"])


@router.get("", response_model=list[CommunicationOut])
def list_communications(
    customer_id: uuid.UUID | None = Query(default=None),
    quote_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    invitation_id: uuid.UUID | None = Query(default=None),
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Communication history for the caller's own tenant.

    With no filter this is the central Communications view (Sprint 039,
    Workstream A); with one it is the timeline on a customer, quote or
    project. One endpoint rather than four, because the only difference
    between those screens is which filter they pass.

    Any authenticated member may read it. Knowing what the workspace has
    sent to its own customers is not a privilege — and the response
    carries no message bodies and no provider internals (see
    CommunicationOut), so there is nothing here an Owner should see that
    a Staff member should not.
    """
    return delivery_service.list_history(
        db,
        current_user.tenant_id,
        customer_id=customer_id,
        quote_id=quote_id,
        project_id=project_id,
        invitation_id=invitation_id,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )


@router.post("/send", response_model=CommunicationOut)
def send_customer_message(
    data: CustomerMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message a person has read and approved (Sprint 039).

    This is the human half of GeoCore AI drafting, and the only way an
    AI-drafted message can ever reach a customer. It takes the reviewed
    text — not a draft id — so what is sent is exactly what was on screen,
    including every edit the person made.

    Declared before `/{communication_id}/retry` because FastAPI matches
    routes in declaration order and "send" would otherwise parse as a UUID.

    Three properties worth stating:

    * **The recipient cannot be chosen.** It is resolved from a Customer
      row this tenant owns. There is no address field, so this is not a
      general-purpose mailer.
    * **Delivery goes through Sprint 038's DeliveryService**, into the
      same ledger as every other send. No second delivery architecture.
    * **A double-click sends once.** The client's idempotency key becomes
      the dedupe key, and DeliveryService already returns the existing row
      for a repeated key rather than sending again.
    """
    customer = crud.get_customer_by_id(db, data.customer_id, current_user.tenant_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )
    if not customer.email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This customer has no email address on file.",
        )

    tenant = crud.get_tenant_by_id(db, current_user.tenant_id)
    rendered = render_customer_message(
        tenant_display_name=tenant.name if tenant is not None else "",
        subject=data.subject,
        body=data.body,
    )
    key = data.idempotency_key or uuid.uuid4().hex
    return delivery_service.send(
        db,
        tenant=tenant,
        message_type=DRAFT_KIND_TO_MESSAGE_TYPE[data.kind],
        recipient=customer.email,
        subject=rendered.subject,
        html=rendered.html,
        text=rendered.text,
        dedupe_key=f"customer_message:{key}",
        customer_id=customer.id,
        quote_id=data.quote_id,
        project_id=data.project_id,
    )


@router.post("/{communication_id}/retry", response_model=CommunicationOut)
def retry_communication(
    communication_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Try a failed message again.

    Goes through the same `DeliveryService.retry()` the scheduled sweep
    uses, which updates the existing row in place. So this cannot create a
    second communication, cannot re-send a delivered one, and cannot push
    past a suppression — not because this route checks for those, but
    because the path underneath it has never been able to.

    A communication that is not in a retryable state is refused with a
    409 rather than silently doing nothing: a button that appears to work
    and does not is worse than one that explains itself.
    """
    try:
        return delivery_service.retry_for_tenant(
            db, current_user.tenant_id, communication_id
        )
    except CommunicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Communication not found"
        )
    except CommunicationNotRetryableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This message can't be retried.",
        )


@router.post("/webhook", include_in_schema=False)
async def resend_webhook(request: Request, db: Session = Depends(get_db)):
    """Public — Resend (via Svix) calls this directly and authenticates
    the request via its signature, not a bearer token. Never trust this
    payload without app.communications.webhooks verifying that signature
    first, and never re-apply its side effects for a delivery already
    processed (Resend/Svix guarantee at-least-once delivery, not
    exactly-once). Same shape as app/billing/router.py's Stripe webhook."""
    if not settings.resend_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email webhook processing is not configured.",
        )

    body = await request.body()
    try:
        verified = verify_svix_signature(
            body=body,
            svix_id=request.headers.get("svix-id"),
            svix_timestamp=request.headers.get("svix-timestamp"),
            svix_signature=request.headers.get("svix-signature"),
            secret=settings.resend_webhook_secret,
        )
    except WebhookSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")

    try:
        event = json.loads(verified.body)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload.")

    if crud.mark_email_event_processed(db, verified.svix_id, event.get("type", "unknown")):
        delivery_service.record_webhook_event(db, event)
    # A replayed delivery (mark_email_event_processed returned False) is
    # acknowledged the same way as a first one — Resend/Svix must never
    # see a different response for a retry, or it will keep retrying.
    return {"received": True}
