"""InvitationService — Sprint 011 (docs/DECISIONS.md ADR-028).

The first module that lets a tenant have more than one user. Token design:
an opaque secrets.token_urlsafe(32) value, hashed with sha256 before it's
ever persisted (token_hash) — never the recoverable secret, same convention
as password_hash. The raw token exists only in create_invitation()'s return
value and the router's one HTTP response; nothing else in the system can
recover it. A DB-backed row (not a self-contained JWT) is required either
way, since the Owner needs to list/revoke pending invites — see ADR-028 for
the full JWT-vs-opaque-token reasoning.

Reuses app.auth.service.auth_service.create_user() to actually create the
Staff user on accept, the same cross-module reuse precedent
AuthService.signup() already set with tenant_service.create().
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.auth.service import auth_service
from app.core.config import settings
from app.database import crud
from app.database.models import Invitation, Tenant, User


class EmailAlreadyRegisteredError(Exception):
    """Raised when the target email already has a `users` row — at invite
    time, or (rarely) again at accept time if it was registered via a
    separate path in between."""


class PendingInvitationExistsError(Exception):
    """Raised when an unresolved invitation already exists for this
    tenant+email — avoids silently issuing a second, different token."""


class InvitationNotFoundError(Exception):
    """Unknown token/id, or an id that belongs to a different tenant.
    Deliberately the same error for both cases — a cross-tenant lookup
    must never confirm another tenant's invitation exists."""


class InvitationNotUsableError(Exception):
    """The invitation was found but is not in a state that can be
    accepted. `reason` is one of "revoked" | "accepted" | "expired"."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class InvitationService:
    def create_invitation(
        self, db: Session, *, tenant_id: uuid.UUID, invited_by_user_id: uuid.UUID, email: str
    ) -> tuple[Invitation, str]:
        """Returns (row, raw_token). role is always UserRole.STAFF this
        sprint — see app/invitations/router.py's docstring for why."""
        if crud.get_user_by_email(db, email) is not None:
            raise EmailAlreadyRegisteredError(email)
        if crud.get_pending_invitation(db, tenant_id, email) is not None:
            raise PendingInvitationExistsError(email)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.invitation_expire_days)

        row = crud.create_invitation(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            invited_by_user_id=invited_by_user_id,
            email=email,
            role=UserRole.STAFF.value,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return row, raw_token

    def get_invitation_by_token(self, db: Session, token: str) -> Invitation | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return crud.get_invitation_by_token_hash(db, token_hash)

    def derive_status(self, row: Invitation) -> str:
        """"expired" is never stored (see Invitation's docstring) — a still-
        "pending" row whose expires_at has passed reads as "expired" here,
        without writing anything back. Used wherever a row's status is
        surfaced (list/public-token views); accept_invitation() does its own
        equivalent check inline since it needs the distinct error reason."""
        if row.status == "pending" and row.expires_at < datetime.now(timezone.utc):
            return "expired"
        return row.status

    def list_invitations(
        self, db: Session, tenant_id: uuid.UUID, status: str | None = None
    ) -> list[Invitation]:
        return crud.list_invitations(db, tenant_id, status=status)

    def revoke_invitation(
        self, db: Session, tenant_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> Invitation:
        row = crud.get_invitation_by_id(db, invitation_id)
        if row is None or row.tenant_id != tenant_id:
            raise InvitationNotFoundError(invitation_id)
        return crud.update_invitation_status(db, invitation_id, status="revoked")

    def accept_invitation(
        self, db: Session, token: str, *, name: str, password: str
    ) -> tuple[Tenant, User]:
        row = self.get_invitation_by_token(db, token)
        if row is None:
            raise InvitationNotFoundError(token)
        if row.status != "pending":
            raise InvitationNotUsableError(row.status)
        if row.expires_at < datetime.now(timezone.utc):
            raise InvitationNotUsableError("expired")
        if crud.get_user_by_email(db, row.email) is not None:
            raise EmailAlreadyRegisteredError(row.email)

        user = auth_service.create_user(
            db,
            tenant_id=row.tenant_id,
            name=name,
            email=row.email,
            password=password,
            role=row.role,
        )
        crud.update_invitation_status(db, row.id, status="accepted")
        tenant = crud.get_tenant_by_id(db, row.tenant_id)
        return tenant, user


invitation_service = InvitationService()
