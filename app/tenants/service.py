"""TenantService — Sprint 008, schema/CRUD only.

Route-level code taking a request-scoped session via get_db(), same pattern
app/customers/ established in Sprint 004 (ADR-019) — no repository-interface
layer, that pattern is for the pre-database era only (ADR-001).

No query here (or anywhere else in the codebase) filters by tenant_id yet —
that's Sprint 012 (see docs/DECISIONS.md ADR-025). This service only
creates/reads rows in the new `tenants` table itself.
"""

import re
import secrets
import uuid

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.database import crud
from app.database.models import Tenant
from app.tenants.models import TenantCreate

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_INVALID_CHARS.sub("-", name.strip().lower()).strip("-")
    return slug or "tenant"


class TenantService:
    def list_all(self, db: Session, limit: int = 20) -> list[Tenant]:
        return crud.list_tenants(db, limit=limit)

    def get(self, db: Session, tenant_id: uuid.UUID | None) -> Tenant | None:
        # Sprint 034 — accepts None so callers working from a row whose
        # tenant_id is still nullable (an anonymous quote, ADR-023) can ask
        # without a guard of their own. No tenant is a real answer here, not
        # an error: the document simply renders without a letterhead.
        if tenant_id is None:
            return None
        return crud.get_tenant_by_id(db, tenant_id)

    def update_identity(self, db: Session, tenant_id: uuid.UUID, data) -> Tenant | None:
        """Sprint 034 — update the tenant's customer-facing company profile.

        Only fields the caller actually sent are written (PATCH semantics),
        so a client that knows about fewer fields than the server can't
        blank out the rest. An empty string clears a field; an omitted one
        leaves it untouched.
        """
        tenant = self.get(db, tenant_id)
        if tenant is None:
            return None

        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(tenant, field, value.strip() or None if isinstance(value, str) else value)

        db.commit()
        db.refresh(tenant)

        if changes:
            activity_service.log(
                ActivityEventCreate(
                    type=ActivityType.TENANT_IDENTITY_UPDATED,
                    title="Company identity updated",
                    description=", ".join(sorted(changes)),
                ),
                tenant_id=tenant.id,
            )
        return tenant

    def create(self, db: Session, data: TenantCreate) -> Tenant:
        slug = data.slug.strip().lower() if data.slug else _slugify(data.name)
        if crud.get_tenant_by_slug(db, slug) is not None:
            # Collision (explicit slug reused, or two auto-generated slugs
            # from similarly-named companies) — retry once with a short
            # random suffix rather than failing the signup outright.
            slug = f"{slug}-{secrets.token_hex(3)}"

        tenant = crud.create_tenant(db, id=uuid.uuid4(), name=data.name, slug=slug)
        # Sprint 008: matches the precedent every other module's create()
        # follows (customers, projects, quotes) — creation and its activity
        # record happen atomically in one place.
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.TENANT_CREATED,
                title="New company workspace created",
                description=tenant.name,
            ),
            tenant_id=tenant.id,
        )
        return tenant


tenant_service = TenantService()
