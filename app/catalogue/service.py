"""CatalogueService — the Master Materials & Supplier Catalogue's
service layer (Sprint 042, GeoCore Premium OS Plan 03). Route-level
pattern (get_db(), no repository interface), per ADR-019, same as
app/quotes/ and app/customers/.
"""

import uuid

from sqlalchemy.orm import Session

from app.catalogue.models import (
    CustomMaterialCreate,
    TenantOverrideIn,
)
from app.database import crud
from app.database.models import CatalogueSurface, CatalogueSurfaceVariant, TenantCatalogueOverride


class SurfaceNotFoundError(Exception):
    def __init__(self, surface_id: uuid.UUID):
        self.surface_id = surface_id
        super().__init__(f"Catalogue surface {surface_id} not found")


def resolve_price_per_slab(override: TenantCatalogueOverride | None) -> float | None:
    """Task 8 — the documented, deterministic precedence rule:

    1. An explicit `selling_price_per_slab` always wins (the tenant
       stated the price outright).
    2. Otherwise, `buy_cost_per_slab` marked up by `default_markup_percent`.
    3. Otherwise, `buy_cost_per_slab` grossed up to hit `target_margin_percent`.
    4. Otherwise `None` — never a fabricated figure. The caller must
       surface this as "no price set for this material" rather than
       defaulting to £0 or any other guessed number (see
       docs/DECISIONS.md for the ADR this precedence is recorded under).

    Margin (not markup) precedence: `price = cost / (1 - margin/100)`,
    the standard gross-margin-target formula — a 25% target margin on a
    £100 cost means £133.33 selling price, not £125 (which would be a
    25% *markup*, a different number).
    """
    if override is None:
        return None
    if override.selling_price_per_slab is not None:
        return override.selling_price_per_slab
    if override.buy_cost_per_slab is None:
        return None
    if override.default_markup_percent is not None:
        return round(override.buy_cost_per_slab * (1 + override.default_markup_percent / 100), 2)
    if override.target_margin_percent is not None:
        if override.target_margin_percent >= 100:
            return None
        return round(override.buy_cost_per_slab / (1 - override.target_margin_percent / 100), 2)
    return None


class CatalogueService:
    def search(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        *,
        query: str | None = None,
        material_family: str | None = None,
        supplier_id: uuid.UUID | None = None,
        manufacturer_id: uuid.UUID | None = None,
        brand_id: uuid.UUID | None = None,
        collection_id: uuid.UUID | None = None,
        colour_family: str | None = None,
        include_discontinued: bool = False,
        limit: int = 20,
    ) -> list[CatalogueSurface]:
        return crud.search_catalogue_surfaces(
            db,
            tenant_id=tenant_id,
            query=query,
            material_family=material_family,
            supplier_id=supplier_id,
            manufacturer_id=manufacturer_id,
            brand_id=brand_id,
            collection_id=collection_id,
            colour_family=colour_family,
            include_discontinued=include_discontinued,
            limit=limit,
        )

    def get_detail(
        self, db: Session, tenant_id: uuid.UUID, surface_id: uuid.UUID
    ) -> tuple[CatalogueSurface, list[CatalogueSurfaceVariant], TenantCatalogueOverride | None]:
        surface = crud.get_catalogue_surface_by_id(db, surface_id, tenant_id)
        if surface is None:
            raise SurfaceNotFoundError(surface_id)
        variants = crud.list_catalogue_surface_variants(db, surface_id)
        override = crud.get_tenant_catalogue_override(db, tenant_id, surface_id, None)
        return surface, variants, override

    def get_tenant_override(
        self, db: Session, tenant_id: uuid.UUID, surface_id: uuid.UUID, surface_variant_id: uuid.UUID | None = None
    ) -> TenantCatalogueOverride | None:
        return crud.get_tenant_catalogue_override(db, tenant_id, surface_id, surface_variant_id)

    def upsert_override(
        self, db: Session, tenant_id: uuid.UUID, surface_id: uuid.UUID, data: TenantOverrideIn
    ) -> TenantCatalogueOverride:
        surface = crud.get_catalogue_surface_by_id(db, surface_id, tenant_id)
        if surface is None:
            raise SurfaceNotFoundError(surface_id)

        fields = data.model_dump(exclude={"surface_variant_id"})
        return crud.upsert_tenant_catalogue_override(
            db,
            tenant_id=tenant_id,
            surface_id=surface_id,
            surface_variant_id=data.surface_variant_id,
            **fields,
        )

    def create_custom_material(
        self, db: Session, tenant_id: uuid.UUID, data: CustomMaterialCreate
    ) -> tuple[CatalogueSurface | None, CatalogueSurfaceVariant | None]:
        """Task 9 — `save_to_catalogue=False` (the default) creates
        nothing durable at all: the caller builds the quote line's
        snapshot straight from `data` and neither a CatalogueSurface nor
        a CatalogueSurfaceVariant row is ever written. `True` persists a
        real, tenant-private (never global) CatalogueSurface + variant
        that can be reused for future quotes — see CatalogueSurface's
        own docstring for the tenant_id=NULL-is-global convention this
        reuses."""
        if not data.save_to_catalogue:
            return None, None

        surface = crud.create_catalogue_surface(
            db,
            tenant_id=tenant_id,
            supplier_id=None,
            manufacturer_id=None,
            brand_id=None,
            collection_id=None,
            canonical_name=data.canonical_name,
            slug=f"tenant-{tenant_id}-{uuid.uuid4().hex[:8]}",
            supplier_sku=None,
            manufacturer_sku=None,
            material_family=data.material_family,
            colour_family=None,
            pattern_family=None,
            origin_country=None,
            active=True,
            discontinued=False,
            source_url=None,
            source_name="tenant_custom",
            source_verified_at=None,
        )
        variant = None
        if data.variant.thickness_mm or data.variant.finish or data.variant.slab_length_mm:
            variant = crud.create_catalogue_surface_variant(
                db,
                surface_id=surface.id,
                thickness_mm=data.variant.thickness_mm,
                finish=data.variant.finish,
                slab_length_mm=data.variant.slab_length_mm,
                slab_width_mm=data.variant.slab_width_mm,
                supplier_variant_sku=None,
                active=True,
            )

        if data.buy_cost_per_slab is not None or data.selling_price_per_slab is not None:
            crud.upsert_tenant_catalogue_override(
                db,
                tenant_id=tenant_id,
                surface_id=surface.id,
                surface_variant_id=None,
                preferred_supplier_id=None,
                supplier_account_ref=None,
                tenant_supplier_sku=None,
                buy_cost_per_slab=data.buy_cost_per_slab,
                buy_cost_per_m2=None,
                delivery_cost=None,
                fabrication_rate=None,
                installation_rate=None,
                default_markup_percent=data.default_markup_percent,
                target_margin_percent=None,
                selling_price_per_slab=data.selling_price_per_slab,
                selling_price_per_m2=None,
                stock_status=None,
                lead_time_days=None,
                tenant_active=True,
                private_notes=None,
            )

        return surface, variant


catalogue_service = CatalogueService()
