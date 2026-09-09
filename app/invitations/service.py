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

Sprint 038 — create_invitation() now also attempts to email the invitee
via DeliveryService, replacing the "copy-paste link only" experience.
This is additive, never a new failure mode for the caller: a delivery
failure (or no provider configured at all) never raises out of
create_invitation() and never prevents the invitation row/raw token from
being created — the manual-link fallback this sprint's own contract
requires (docs/SPRINTS/sprint-038.md §3) stays fully intact regardless of
whether the email send succeeded. The router surfaces the real outcome
separately (InvitationOut.delivery_status).
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.models import UserRole
from app.auth.service import auth_service
from app.communications.models import CommunicationType
from app.communications.service import DeliveryService, delivery_service
from app.communications.templates import render_invitation
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
    def __init__(self, delivery: DeliveryService | None = None) -> None:
        # Constructor-injectable, same DI shape as DeliveryService's own
        # provider param — tests pass a fake/mock DeliveryService rather
        # than reaching into a private attribute.
        self._delivery = delivery or delivery_service

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
        self._send_invitation_email(
            db, row, raw_token=raw_token, invited_by_user_id=invited_by_user_id
        )
        return row, raw_token

    def _send_invitation_email(
        self, db: Session, row: Invitation, *, raw_token: str, invited_by_user_id: uuid.UUID
    ) -> None:
        """Best-effort — see this module's own docstring for why nothing
        here ever raises out to the caller. The raw token/link is already
        safely returned to the caller by create_invitation() regardless of
        what happens in here.

        Uses `raw_token` (never `row.id`) in the accept URL — the frontend
        route and the public `/invitations/token/{token}` endpoint both
        key off the opaque token, not the row's internal id; the id alone
        cannot accept an invitation."""
        try:
            tenant = crud.get_tenant_by_id(db, row.tenant_id)
            inviter = crud.get_user_by_id(db, invited_by_user_id)
            inviter_name = inviter.name if inviter is not None else "A teammate"
            tenant_display_name = tenant.name if tenant is not None else "your team"

            accept_url = f"{settings.frontend_base_url}/invite/{raw_token}"
            rendered = render_invitation(
                tenant_display_name=tenant_display_name,
                inviter_name=inviter_name,
                accept_url=accept_url,
            )
            self._delivery.send(
                db,
                tenant=tenant,
                message_type=CommunicationType.INVITATION,
                recipient=row.email,
                subject=rendered.subject,
                html=rendered.html,
                text=rendered.text,
                dedupe_key=f"invitation:{row.id}",
                invitation_id=row.id,
            )
        except Exception:
            # Anything unexpected here (a DB hiccup building the row, a
            # provider surprise DeliveryService itself didn't catch) must
            # never take down invitation creation, which has already
            # committed by this point. Deliberately broad and silent at
            # this layer — DeliveryService is the place failures are
            # actually recorded (in the communications table, inspectable
            # by the Owner); this except exists only to guarantee
            # create_invitation()'s own contract, not to hide the failure
            # from history.
            pass

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
