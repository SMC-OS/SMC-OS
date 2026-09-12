"""PasswordResetService — Sprint 039 Production Readiness Defect Gate,
Blocker 2 (docs/SPRINTS/sprint-039.md).

Token design mirrors app/invitations/service.py and Blocker 1's
verification_service.py exactly: an opaque secrets.token_urlsafe(32)
value, hashed with sha256 before it's ever persisted (token_hash) — never
the recoverable secret. The raw token exists only in request_reset()'s
send call and the link it builds; nothing else in the system can recover
it.

Sends through app/communications' DeliveryService (Resend), the same path
every other outbound email in this codebase uses — not a new, parallel
email pathway. A delivery failure (or no provider configured at all)
never raises out of request_reset(): the caller's own no-enumeration
response is identical either way (see app/auth/router.py's forgot_password
route), matching InvitationService's "never a new failure mode for the
caller" precedent.

No-enumeration by construction, not by convention: request_reset() always
returns None (there is nothing for it to leak), and it is deliberately the
router's job — not this service's — to decide whether an account exists
for logging purposes only, never for the HTTP response shape.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.communications.models import CommunicationType
from app.communications.service import DeliveryService, delivery_service
from app.communications.templates import render_password_reset
from app.core.config import settings
from app.database import crud
from app.database.models import User


class ResetTokenInvalidError(Exception):
    """Unknown token hash, already-used token, or expired token —
    deliberately the same error for all three so a reset attempt never
    reveals which specific reason applies."""


class PasswordResetService:
    def __init__(self, delivery: DeliveryService | None = None) -> None:
        # Constructor-injectable, same DI shape as InvitationService's and
        # EmailVerificationService's own `delivery` param — tests pass a
        # fake/mock DeliveryService rather than reaching into a private
        # attribute.
        self._delivery = delivery or delivery_service

    def request_reset(self, db: Session, email: str) -> None:
        """Best-effort, silent on every outcome (unknown email, delivery
        failure, no provider configured) — see this module's own
        docstring for why. Returns nothing; the caller's response never
        varies based on what happened here."""
        user = crud.get_user_by_email(db, email)
        if user is None:
            return

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.password_reset_token_expire_hours
        )
        row = crud.create_password_reset_token(
            db,
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        try:
            tenant = crud.get_tenant_by_id(db, user.tenant_id)
            tenant_display_name = tenant.name if tenant is not None else "GeoCore"
            reset_url = f"{settings.frontend_base_url}/reset-password?token={raw_token}"
            rendered = render_password_reset(
                tenant_display_name=tenant_display_name,
                recipient_name=user.name,
                reset_url=reset_url,
            )
            self._delivery.send(
                db,
                tenant=tenant,
                message_type=CommunicationType.PASSWORD_RESET,
                recipient=user.email,
                subject=rendered.subject,
                html=rendered.html,
                text=rendered.text,
                dedupe_key=f"password-reset:{row.id}",
            )
        except Exception:
            # Same reasoning as InvitationService/EmailVerificationService:
            # anything unexpected here must never take down the caller,
            # which has already committed the token row by this point.
            pass

    def reset_password(self, db: Session, raw_token: str, new_password: str) -> User:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        row = crud.get_password_reset_token_by_hash(db, token_hash)
        now = datetime.now(timezone.utc)
        if row is None or row.used_at is not None or row.expires_at < now:
            raise ResetTokenInvalidError(raw_token)

        crud.mark_password_reset_token_used(db, row.id, now)
        user = crud.set_user_password(db, row.user_id, password_hash=hash_password(new_password))
        if user is None:
            # The token's own user_id FK guarantees this row cannot exist
            # without a real user; only reachable if that user row was
            # hard-deleted between the lookup above and here.
            raise ResetTokenInvalidError(raw_token)
        return user


password_reset_service = PasswordResetService()
