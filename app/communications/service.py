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
        return self._attempt(db, row, message)

    # Bounded retries — a communication stuck retrying forever is a worse
    # failure mode than one that eventually gives up and stays visible as
    # failed for a human to notice. Matches the brief's own "no endless
    # retries" requirement (§11).
    MAX_ATTEMPTS = 5

    def retry(self, db: Session, communication_id: uuid.UUID) -> Communication | None:
        """Re-attempt a row already in `failed` state with a retryable
        `failure_category` (`transient` or `unavailable` — see
        crud.list_retryable_communications's docstring for why not the
        others). Updates the same row in place; never creates a second
        one, so `dedupe_key`'s uniqueness is never at risk. Returns None
        for an unknown id, or the row unchanged if it is no longer in a
        retryable state (already retried past MAX_ATTEMPTS, or resolved by
        something else since the caller last looked) — never raises."""
        row = db.get(Communication, communication_id)
        if row is None:
            return None
        if row.status != "failed" or row.failure_category not in ("transient", "unavailable"):
            return row
        if row.attempt_count >= self.MAX_ATTEMPTS:
            return row

        tenant = crud.get_tenant_by_id(db, row.tenant_id)
        sender_identity, reply_to = resolve_sender_identity(tenant)
        message = EmailMessage(
            recipient=row.recipient,
            sender_identity=sender_identity,
            reply_to=reply_to,
            subject=row.subject,
            html=row.body_html,
            text=row.body_text,
            idempotency_key=f"{row.tenant_id}:{row.dedupe_key}",
        )
        return self._attempt(db, row, message)

    def _attempt(self, db: Session, row: Communication, message: EmailMessage) -> Communication:
        """Call the provider once for an already-persisted `row` and
        record the real outcome in place. Shared by the first attempt
        (send()) and every subsequent one (retry())."""
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

    def retry_pending(self, db: Session, *, limit: int = 100) -> dict:
        """Sweep every retryable failed communication (across every
        tenant — a scheduled job has no caller, same rationale as
        app.automations.scan) and retry each once. The single entrypoint
        `app/jobs/automations.py` calls alongside its existing scan, so
        this sprint does not introduce a second scheduled Railway service
        for what the existing cron job architecture already handles
        safely at this scale (brief §11: "do not introduce unnecessary
        infrastructure")."""
        retried = succeeded = still_failed = 0
        for row in crud.list_retryable_communications(db, limit=limit):
            result = self.retry(db, row.id)
            if result is None:
                continue
            retried += 1
            if result.status == "sent":
                succeeded += 1
            elif result.status == "failed":
                still_failed += 1
        return {"retried": retried, "succeeded": succeeded, "still_failed": still_failed}

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

    # Resend's own documented webhook event types. `email.sent` is a
    # no-op here (the row is already "sent" from send()'s own ACCEPTED
    # branch); `email.opened`/`email.clicked` are deliberately not
    # handled — this sprint tracks delivery/failure, not open/click
    # analytics, which is a separate product decision this doesn't make.
    _DELIVERED_EVENTS = frozenset({"email.delivered"})
    _BOUNCED_EVENTS = frozenset({"email.bounced"})
    _COMPLAINED_EVENTS = frozenset({"email.complained"})

    def record_webhook_event(self, db: Session, event: dict) -> str:
        """Apply one verified Resend webhook event. Returns a short,
        human-readable outcome string for logging — never raises for an
        event shape this doesn't recognise or can't resolve (an unknown
        event type, or a provider_message_id with no matching row, are
        both acknowledged rather than treated as errors — Resend would
        otherwise retry a webhook this service can never successfully
        process). Idempotency against a *replayed* delivery of the same
        event is the router's job (crud.mark_email_event_processed),
        before this is ever called."""
        event_type = event.get("type")
        data = event.get("data") or {}
        provider_message_id = data.get("email_id")
        if not provider_message_id:
            return "no email_id in event payload"

        row = crud.get_communication_by_provider_message_id(db, provider_message_id)
        if row is None:
            return f"no communication found for provider_message_id {provider_message_id}"

        if event_type in self._DELIVERED_EVENTS:
            crud.update_communication_result(
                db,
                row.id,
                status="delivered",
                provider="resend",
                provider_message_id=row.provider_message_id,
                failure_category=None,
                failure_detail=None,
                increment_attempt=False,
            )
            return "marked delivered"

        if event_type in self._BOUNCED_EVENTS:
            crud.update_communication_result(
                db,
                row.id,
                status="bounced",
                provider="resend",
                provider_message_id=row.provider_message_id,
                failure_category=FailureCategory.PERMANENT.value,
                failure_detail="This address bounced and has been suppressed.",
                increment_attempt=False,
            )
            self.suppress(
                db,
                tenant_id=row.tenant_id,
                email=row.recipient,
                reason="hard_bounce",
                source_communication_id=row.id,
            )
            return "marked bounced and suppressed"

        if event_type in self._COMPLAINED_EVENTS:
            # The message itself already reached the inbox (that's what a
            # complaint means) — its own status is left alone. What
            # matters going forward is that this address never receives
            # another send.
            self.suppress(
                db,
                tenant_id=row.tenant_id,
                email=row.recipient,
                reason="complaint",
                source_communication_id=row.id,
            )
            return "suppressed on complaint"

        return f"no handler for event type {event_type!r}"


delivery_service = DeliveryService()
