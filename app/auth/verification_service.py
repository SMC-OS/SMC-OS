"""EmailVerificationService — Sprint 039 Production Readiness Defect Gate,
Blocker 1 (docs/SPRINTS/sprint-039.md).

Token design mirrors app/invitations/service.py exactly: an opaque
secrets.token_urlsafe(32) value, hashed with sha256 before it's ever
persisted (token_hash) — never the recoverable secret. The raw token exists
only in send_verification_email()'s send call and the link it builds;
nothing else in the system can recover it.

Sends through app/communications' DeliveryService (Resend), the same path
every other outbound email in this codebase uses since Sprint 038 — not a
new, parallel email pathway. A delivery failure (or no provider configured
at all) never raises out of send_verification_email(): the token row is
always created so the link the caller already has stays valid regardless of
whether the email itself got through, matching InvitationService's own
"never a new failure mode for the caller" precedent.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.communications.models import CommunicationType
from app.communications.service import DeliveryService, delivery_service
from app.communications.templates import render_email_verification
from app.core.config import settings
from app.database import crud
from app.database.models import User


class VerificationTokenInvalidError(Exception):
    """Unknown token hash, already-used token, or expired token —
    deliberately the same error for all three so a confirm attempt never
    reveals which specific reason applies."""


class EmailVerificationService:
    def __init__(self, delivery: DeliveryService | None = None) -> None:
        # Constructor-injectable, same DI shape as InvitationService's own
        # `delivery` param — tests pass a fake/mock DeliveryService rather
        # than reaching into a private attribute.
        self._delivery = delivery or delivery_service

    def send_verification_email(self, db: Session, user: User) -> None:
        """Best-effort — see this module's own docstring for why nothing
        here ever raises out to the caller."""
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.email_verification_token_expire_hours
        )
        row = crud.create_email_verification_token(
            db,
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        try:
            tenant = crud.get_tenant_by_id(db, user.tenant_id)
            tenant_display_name = tenant.name if tenant is not None else "GeoCore"
            verify_url = f"{settings.frontend_base_url}/verify-email?token={raw_token}"
            rendered = render_email_verification(
                tenant_display_name=tenant_display_name,
                recipient_name=user.name,
                verify_url=verify_url,
            )
            self._delivery.send(
                db,
                tenant=tenant,
                message_type=CommunicationType.EMAIL_VERIFICATION,
                recipient=user.email,
                subject=rendered.subject,
                html=rendered.html,
                text=rendered.text,
                dedupe_key=f"email-verification:{row.id}",
            )
        except Exception:
            # Same reasoning as InvitationService._send_invitation_email:
            # anything unexpected here must never take down the caller,
            # which has already committed the token row by this point.
            # DeliveryService is the place failures are actually recorded
            # (in the communications table); this except only guarantees
            # send_verification_email()'s own contract.
            pass

    def verify(self, db: Session, raw_token: str) -> User:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        row = crud.get_email_verification_token_by_hash(db, token_hash)
        now = datetime.now(timezone.utc)
        if row is None or row.used_at is not None or row.expires_at < now:
            raise VerificationTokenInvalidError(raw_token)

        crud.mark_email_verification_token_used(db, row.id, now)
        user = crud.set_user_email_verified_at(db, row.user_id, now)
        if user is None:
            # The token's own user_id FK guarantees this row cannot exist
            # without a real user; only reachable if that user row was
            # hard-deleted between the lookup above and here.
            raise VerificationTokenInvalidError(raw_token)
        return user


email_verification_service = EmailVerificationService()
