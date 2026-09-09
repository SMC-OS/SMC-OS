"""DeliveryService (Sprint 038, docs/SPRINTS/sprint-038.md §3 and §6).

The one thing app/invitations, app/quotes and app/automations call to send
anything. It never lets a delivery failure — or an unconfigured provider —
raise past its own boundary: `send()` always returns a `Communication` row,
whose `status`/`failure_category` tell the caller (and, from there, the
user) truthfully what happened. Nothing upstream of this module ever
fabricates a "sent" state.

Ordering inside `send()` matters and is deliberate:

1. Dedupe check first — a retried caller (a double-click, a retried worker
   tick) gets back the existing row unchanged, never a second send.
2. Suppression check next — before any row is even created with a
   "queued" status, so a suppressed recipient never shows as briefly
   queued in history.
3. The `communications` row is written with status "queued" and
   committed *before* the provider is ever called — a crash mid-send
   still leaves an inspectable, honest row (matches the same reasoning
   ADR-035's migrate_gate and the Stripe webhook's mark-processed-first
   ordering already use elsewhere in this codebase).
4. Only then is the provider called, and the row updated in place with
   the real outcome.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.communications.models import CommunicationType, FailureCategory
from app.communications.provider import (
    EmailMessage,
    EmailProvider,
    EmailProviderUnavailable,
    ResendEmailProvider,
    SendOutcome,
    resolve_sender_identity,
)
from app.database import crud
from app.database.models import Communication


class DeliveryService:
    def __init__(self, provider: EmailProvider | None = None) -> None:
        # Constructor-injectable, same pattern as BillingService — tests
        # pass a fake/mock EmailProvider directly rather than reaching
        # into a private attribute.
        self._provider = provider or ResendEmailProvider()

    def send(
        self,
        db: Session,
        *,
        tenant,
        message_type: CommunicationType,
        recipient: str,
        subject: str,
        html: str,
        text: str,
        dedupe_key: str,
        customer_id: uuid.UUID | None = None,
        quote_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        invitation_id: uuid.UUID | None = None,
        automation_id: uuid.UUID | None = None,
        automation_run_id: uuid.UUID | None = None,
    ) -> Communication:
        tenant_id = tenant.id if tenant is not None else None
        if tenant_id is None:
            raise ValueError("DeliveryService.send() requires a tenant")

        existing = crud.get_communication_by_dedupe_key(db, tenant_id, dedupe_key)
        if existing is not None:
            return existing

        recipient_normalized = recipient.strip().lower()
        suppression = crud.get_email_suppression(db, tenant_id, recipient_normalized)
        sender_identity, reply_to = resolve_sender_identity(tenant)

        row = crud.create_communication(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            message_type=message_type.value,
            recipient=recipient_normalized,
            sender_identity=sender_identity,
            subject=subject,
            body_html=html,
            body_text=text,
            dedupe_key=dedupe_key,
            status="queued",
            customer_id=customer_id,
            quote_id=quote_id,
            project_id=project_id,
            invitation_id=invitation_id,
            automation_id=automation_id,
            automation_run_id=automation_run_id,
        )

        if suppression is not None:
            return crud.update_communication_result(
                db,
                row.id,
                status="suppressed",
                failure_category=FailureCategory.SUPPRESSED.value,
                failure_detail="This address is on the suppression list and was not sent to.",
                last_attempted_at=datetime.now(timezone.utc),
            )

        message = EmailMessage(
            recipient=recipient_normalized,
            sender_identity=sender_identity,
            reply_to=reply_to,
            subject=subject,
            html=html,
            text=text,
            idempotency_key=f"{tenant_id}:{dedupe_key}",
        )

        try:
            result = self._provider.send(message)
        except EmailProviderUnavailable as exc:
            return crud.update_communication_result(
                db,
                row.id,
                status="failed",
                failure_category=FailureCategory.UNAVAILABLE.value,
                failure_detail=str(exc),
                last_attempted_at=datetime.now(timezone.utc),
            )

        now = datetime.now(timezone.utc)
        if result.outcome == SendOutcome.ACCEPTED:
            return crud.update_communication_result(
                db,
                row.id,
                status="sent",
                provider="resend",
                provider_message_id=result.provider_message_id,
                failure_category=None,
                failure_detail=None,
                last_attempted_at=now,
            )

        failure_category = (
            FailureCategory.TRANSIENT
            if result.outcome == SendOutcome.TRANSIENT_FAILURE
            else FailureCategory.PERMANENT
        )
        return crud.update_communication_result(
            db,
            row.id,
            status="failed",
            provider="resend",
            failure_category=failure_category.value,
            failure_detail=result.detail,
            last_attempted_at=now,
        )

    def list_history(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None = None,
        quote_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        invitation_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[Communication]:
        return crud.list_communications(
            db,
            tenant_id,
            customer_id=customer_id,
            quote_id=quote_id,
            project_id=project_id,
            invitation_id=invitation_id,
            limit=limit,
        )

    def suppress(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        email: str,
        reason: str,
        source_communication_id: uuid.UUID | None = None,
    ):
        email_normalized = email.strip().lower()
        existing = crud.get_email_suppression(db, tenant_id, email_normalized)
        if existing is not None:
            return existing
        return crud.create_email_suppression(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=email_normalized,
            reason=reason,
            source_communication_id=source_communication_id,
        )


delivery_service = DeliveryService()
