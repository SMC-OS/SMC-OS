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
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.database import crud
from app.database.models import Tenant
from app.projects import pipeline_config
from app.tenants.models import (
    OnboardingStateOut,
    TenantCreate,
    TenantOnboardingUpdate,
    TenantProfileOut,
)
from app.trades import catalogue as trade_catalogue

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

    # ------------------------------------------------------------------
    # Sprint 036 — workspace configuration and onboarding.
    # ------------------------------------------------------------------

    def to_profile(self, tenant: Tenant) -> TenantProfileOut:
        """Serialise a Tenant row into the profile clients read.

        Written by hand rather than left to `from_attributes` because two
        fields do not map straight across: `trades` is stored as a
        comma-separated string and exposed as a list, and
        `has_uploaded_logo` is a flag derived from a storage filename that
        must never itself reach a client.
        """
        return TenantProfileOut(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            status=tenant.status,
            created_at=tenant.created_at,
            legal_name=tenant.legal_name,
            trading_name=tenant.trading_name,
            address_line1=tenant.address_line1,
            address_line2=tenant.address_line2,
            city=tenant.city,
            postcode=tenant.postcode,
            country=tenant.country,
            contact_email=tenant.contact_email,
            contact_phone=tenant.contact_phone,
            website=tenant.website,
            company_number=tenant.company_number,
            vat_number=tenant.vat_number,
            logo_url=tenant.logo_url,
            document_footer=tenant.document_footer,
            currency=tenant.currency or "GBP",
            trades=trade_catalogue.parse_selection(tenant.trades),
            onboarding_completed_at=tenant.onboarding_completed_at,
            has_uploaded_logo=bool(tenant.logo_storage_filename),
        )

    def update_onboarding(
        self, db: Session, tenant_id: uuid.UUID, data: TenantOnboardingUpdate
    ) -> Tenant | None:
        tenant = self.get(db, tenant_id)
        if tenant is None:
            return None

        changes = data.model_dump(exclude_unset=True)
        if "trades" in changes and changes["trades"] is not None:
            # Serialised in catalogue order and de-duplicated, so the
            # stored value is stable regardless of the order the user
            # happened to click the options in.
            tenant.trades = trade_catalogue.serialize_selection(changes["trades"])
        if changes.get("currency"):
            tenant.currency = changes["currency"]
        if data.complete and tenant.onboarding_completed_at is None:
            # Only ever set once. Re-running the flow to change a trade
            # selection must not rewrite the date the workspace was
            # actually set up.
            tenant.onboarding_completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(tenant)
        return tenant

    def onboarding_state(self, db: Session, tenant_id: uuid.UUID) -> OnboardingStateOut | None:
        tenant = self.get(db, tenant_id)
        if tenant is None:
            return None

        # A workspace that is already being used is finished, whatever the
        # column says. Every tenant that existed before Sprint 036 has a
        # NULL onboarding_completed_at, and sending an established business
        # back through a setup wizard would be a regression dressed as a
        # feature. Any real record is proof enough.
        workspace_has_data = (
            crud.count_customers(db, tenant_id) > 0
            or crud.count_projects(db, tenant_id) > 0
            or len(crud.list_quotes(db, tenant_id, limit=1)) > 0
        )

        has_identity = any(
            bool(getattr(tenant, field, None))
            for field in ("legal_name", "trading_name", "address_line1", "contact_phone")
        )
        invitations = crud.list_invitations(db, tenant_id)

        return OnboardingStateOut(
            required=tenant.onboarding_completed_at is None and not workspace_has_data,
            completed_at=tenant.onboarding_completed_at,
            trades=trade_catalogue.parse_selection(tenant.trades),
            currency=tenant.currency or "GBP",
            has_company_identity=has_identity,
            has_team_invitations=bool(invitations),
            workspace_has_data=workspace_has_data,
        )

    def set_logo_file(
        self, db: Session, tenant_id: uuid.UUID, storage_filename: str | None
    ) -> Tenant | None:
        tenant = self.get(db, tenant_id)
        if tenant is None:
            return None
        tenant.logo_storage_filename = storage_filename
        db.commit()
        db.refresh(tenant)
        return tenant

    def create(self, db: Session, data: TenantCreate) -> Tenant:
        slug = data.slug.strip().lower() if data.slug else _slugify(data.name)
        if crud.get_tenant_by_slug(db, slug) is not None:
            # Collision (explicit slug reused, or two auto-generated slugs
            # from similarly-named companies) — retry once with a short
            # random suffix rather than failing the signup outright.
            slug = f"{slug}-{secrets.token_hex(3)}"

        tenant = crud.create_tenant(db, id=uuid.uuid4(), name=data.name, slug=slug)
        # Sprint 039 (Workstream D) — a new workspace gets GeoCore's
        # trade-neutral pipeline. This is the single choke point every
        # tenant is created through, so no signup path can produce a
        # workspace with no stages; pipeline_config.resolve() still falls
        # back to the same template if one ever somehow does.
        pipeline_config.seed_for_tenant(db, tenant.id)
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
