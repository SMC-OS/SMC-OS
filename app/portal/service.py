"""PortalService — Sprint 013 (docs/DECISIONS.md ADR-030).

Read-only client portal: a customer views their own projects/quotes with
no account, no login, no `users` row. Token design mirrors
app/invitations/service.py exactly — an opaque secrets.token_urlsafe(32)
value, hashed with sha256 before it's ever persisted (token_hash), never
the recoverable secret. The one behavioral difference: a portal link is
NOT single-use. There is no "accept" step and no "accepted" status —
status is only "active" | "revoked", and every GET against an active,
unexpired token just re-reads the current data, unlimited times, until an
Owner/Staff revokes it or it expires.

Tenant isolation (ADR-029) from the start, not deferred: create_link()
validates the given customer_id resolves under the caller's own tenant
before creating a row (crud.get_customer_by_id is already tenant-scoped),
and get_public_view() resolves tenant_id/customer_id from the token row
itself, never from caller input — a token minted under tenant A cannot
structurally surface tenant B's data.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import crud
from app.database.models import Customer, PortalLink, Project, Quote, Tenant


class CustomerNotFoundError(Exception):
    """Raised by create_link() when customer_id doesn't resolve under the
    caller's own tenant — the same relationship-linkage bypass check
    ADR-029 added to app/projects/service.py and app/quotes/service.py."""


class PortalLinkNotFoundError(Exception):
    """Unknown token/id, or an id that belongs to a different tenant.
    Deliberately the same error for both cases — a cross-tenant lookup
    must never confirm another tenant's portal link exists (ADR-028's
    precedent)."""


class PortalService:
    def create_link(
        self, db: Session, *, tenant_id: uuid.UUID, created_by_user_id: uuid.UUID, customer_id: uuid.UUID
    ) -> tuple[PortalLink, str]:
        """Returns (row, raw_token)."""
        if crud.get_customer_by_id(db, customer_id, tenant_id) is None:
            raise CustomerNotFoundError(customer_id)

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.portal_link_expire_days)

        row = crud.create_portal_link(
            db,
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            customer_id=customer_id,
            created_by_user_id=created_by_user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return row, raw_token

    def get_link_by_token(self, db: Session, token: str) -> PortalLink | None:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return crud.get_portal_link_by_token_hash(db, token_hash)

    def derive_status(self, row: PortalLink) -> str:
        """"expired" is never stored (see PortalLink's docstring) — a
        still-"active" row whose expires_at has passed reads as "expired"
        here, without writing anything back."""
        if row.status == "active" and row.expires_at < datetime.now(timezone.utc):
            return "expired"
        return row.status

    def list_links(
        self, db: Session, tenant_id: uuid.UUID, customer_id: uuid.UUID | None = None
    ) -> list[PortalLink]:
        return crud.list_portal_links(db, tenant_id, customer_id=customer_id)

    def revoke_link(self, db: Session, tenant_id: uuid.UUID, portal_link_id: uuid.UUID) -> PortalLink:
        row = crud.get_portal_link_by_id(db, portal_link_id)
        if row is None or row.tenant_id != tenant_id:
            raise PortalLinkNotFoundError(portal_link_id)
        return crud.update_portal_link_status(db, portal_link_id, status="revoked")

    def get_public_view(
        self, db: Session, token: str
    ) -> tuple[PortalLink, str, Tenant | None, Customer | None, list[Project], list[Quote]]:
        """Returns (row, status, tenant, customer, projects, quotes).
        projects/quotes are only populated for an "active" status — a
        revoked or expired link still resolves tenant/customer name (same
        "always 200, status tells the story" convention InvitationPublicOut
        uses) but never leaks the underlying business data. The row itself
        is returned so the caller can read expires_at without a second
        lookup."""
        row = self.get_link_by_token(db, token)
        if row is None:
            raise PortalLinkNotFoundError(token)

        status = self.derive_status(row)
        tenant = crud.get_tenant_by_id(db, row.tenant_id)
        customer = crud.get_customer_by_id(db, row.customer_id, row.tenant_id)

        if status != "active":
            return row, status, tenant, customer, [], []

        projects = crud.list_projects_by_customer(db, row.tenant_id, row.customer_id)
        quotes = crud.list_quotes_by_customer(db, row.tenant_id, row.customer_id)
        return row, status, tenant, customer, projects, quotes

    def get_customer_quote(self, db: Session, token: str, quote_id: uuid.UUID) -> Quote:
        """Resolves one quote for invoice download. The token must be
        active (an expired/revoked link serves no PDF — unlike
        get_public_view()'s "still 200, just empty" convention, there's no
        empty-PDF equivalent), and the quote must belong to both the
        token's tenant_id AND its customer_id — not tenant alone, or one
        portal link could pull a different customer's invoice within the
        same tenant. Every failure raises the same PortalLinkNotFoundError
        so a caller can't distinguish "bad token" from "quote not yours."
        """
        row = self.get_link_by_token(db, token)
        if row is None or self.derive_status(row) != "active":
            raise PortalLinkNotFoundError(token)

        quote = crud.get_quote_by_id(db, quote_id, row.tenant_id)
        if quote is None or quote.customer_id != row.customer_id:
            raise PortalLinkNotFoundError(quote_id)
        return quote


portal_service = PortalService()
