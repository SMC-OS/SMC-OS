"""Master Materials & Supplier Catalogue HTTP surface (Sprint 042).

Router-level `require_billing_access` baseline (same shape as
app/quotes/router.py) — any authorised, billed tenant user can browse
and search the catalogue. Writing a tenant's own commercial override is
Owner-only (Task 16: "tenant commercial overrides: owner/admin" — this
codebase has no admin role distinct from Owner, see app/auth/models.py's
UserRole, so Owner is the exact match, not a new parallel permission
concept). Creating a custom material (used inline while quoting) is any
authorised quoting role (Owner/Staff), matching app/quotes/router.py's
own general-quote-creation gate exactly.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_billing_access, require_role
from app.auth.models import UserRole
from app.catalogue.models import (
    MATERIAL_FAMILIES,
    CatalogueStatusOut,
    CustomMaterialCreate,
    CustomMaterialOut,
    SurfaceDetailOut,
    SurfaceSearchResult,
    TenantOverrideIn,
    TenantOverrideOut,
)
from app.catalogue.service import SurfaceNotFoundError, catalogue_service, resolve_price_per_slab
from app.database.database import get_db
from app.database.models import CatalogueSurface, User

router = APIRouter(prefix="/catalogue", tags=["catalogue"], dependencies=[Depends(require_billing_access)])


def _name_lookup(db: Session, model, obj_id: uuid.UUID | None) -> str | None:
    if obj_id is None:
        return None
    row = db.get(model, obj_id)
    return row.name if row is not None else None


def _serialize_search_result(db: Session, surface: CatalogueSurface, tenant_id: uuid.UUID) -> SurfaceSearchResult:
    from app.database.models import CatalogueBrand, CatalogueCollection, CatalogueManufacturer, CatalogueSupplier

    variants = _list_variants(db, surface.id)
    override = _get_override(db, tenant_id, surface.id)
    return SurfaceSearchResult(
        id=surface.id,
        canonical_name=surface.canonical_name,
        material_family=surface.material_family,
        colour_family=surface.colour_family,
        supplier_name=_name_lookup(db, CatalogueSupplier, surface.supplier_id),
        manufacturer_name=_name_lookup(db, CatalogueManufacturer, surface.manufacturer_id),
        brand_name=_name_lookup(db, CatalogueBrand, surface.brand_id),
        collection_name=_name_lookup(db, CatalogueCollection, surface.collection_id),
        active=surface.active,
        discontinued=surface.discontinued,
        is_tenant_private=surface.tenant_id is not None,
        thicknesses_mm=sorted({v.thickness_mm for v in variants if v.thickness_mm is not None}),
        finishes=sorted({v.finish for v in variants if v.finish}),
        has_tenant_price=resolve_price_per_slab(override) is not None,
    )


def _list_variants(db: Session, surface_id: uuid.UUID):
    from app.database import crud

    return crud.list_catalogue_surface_variants(db, surface_id)


def _get_override(db: Session, tenant_id: uuid.UUID, surface_id: uuid.UUID):
    from app.database import crud

    return crud.get_tenant_catalogue_override(db, tenant_id, surface_id, None)


@router.get("/meta/material-families", response_model=list[str])
def list_material_families():
    return sorted(MATERIAL_FAMILIES)


@router.get("/meta/status", response_model=CatalogueStatusOut)
def get_catalogue_status(
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    from app.database import crud

    counts = crud.count_visible_catalogue_surfaces(db, current_user.tenant_id)
    return CatalogueStatusOut(
        global_surfaces=counts["global_surfaces"],
        tenant_surfaces=counts["tenant_surfaces"],
        reference_data_loaded=counts["global_surfaces"] > 0,
    )


@router.get("/surfaces", response_model=list[SurfaceSearchResult])
def search_surfaces(
    q: str | None = None,
    material_family: str | None = None,
    supplier_id: uuid.UUID | None = None,
    manufacturer_id: uuid.UUID | None = None,
    brand_id: uuid.UUID | None = None,
    collection_id: uuid.UUID | None = None,
    colour_family: str | None = None,
    include_discontinued: bool = False,
    limit: int = 20,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    surfaces = catalogue_service.search(
        db,
        current_user.tenant_id,
        query=q,
        material_family=material_family,
        supplier_id=supplier_id,
        manufacturer_id=manufacturer_id,
        brand_id=brand_id,
        collection_id=collection_id,
        colour_family=colour_family,
        include_discontinued=include_discontinued,
        limit=limit,
    )
    return [_serialize_search_result(db, surface, current_user.tenant_id) for surface in surfaces]


@router.get("/surfaces/{surface_id}", response_model=SurfaceDetailOut)
def get_surface_detail(
    surface_id: uuid.UUID,
    current_user: User = Depends(require_billing_access),
    db: Session = Depends(get_db),
):
    from app.database.models import CatalogueBrand, CatalogueCollection, CatalogueManufacturer, CatalogueSupplier

    try:
        surface, variants, override = catalogue_service.get_detail(db, current_user.tenant_id, surface_id)
    except SurfaceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalogue surface not found")

    override_out = None
    if override is not None:
        override_out = TenantOverrideOut.model_validate(override).model_copy(
            update={"resolved_price_per_slab": resolve_price_per_slab(override)}
        )

    return SurfaceDetailOut(
        id=surface.id,
        is_tenant_private=surface.tenant_id is not None,
        canonical_name=surface.canonical_name,
        material_family=surface.material_family,
        colour_family=surface.colour_family,
        pattern_family=surface.pattern_family,
        origin_country=surface.origin_country,
        supplier=db.get(CatalogueSupplier, surface.supplier_id) if surface.supplier_id else None,
        manufacturer=db.get(CatalogueManufacturer, surface.manufacturer_id) if surface.manufacturer_id else None,
        brand=db.get(CatalogueBrand, surface.brand_id) if surface.brand_id else None,
        collection=db.get(CatalogueCollection, surface.collection_id) if surface.collection_id else None,
        supplier_sku=surface.supplier_sku,
        manufacturer_sku=surface.manufacturer_sku,
        active=surface.active,
        discontinued=surface.discontinued,
        source_name=surface.source_name,
        source_url=surface.source_url,
        source_verified_at=surface.source_verified_at,
        variants=variants,
        tenant_override=override_out,
    )


@router.put("/surfaces/{surface_id}/override", response_model=TenantOverrideOut)
def upsert_tenant_override(
    surface_id: uuid.UUID,
    data: TenantOverrideIn,
    current_user: User = Depends(require_role(UserRole.OWNER)),
    db: Session = Depends(get_db),
):
    try:
        override = catalogue_service.upsert_override(db, current_user.tenant_id, surface_id, data)
    except SurfaceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalogue surface not found")

    return TenantOverrideOut.model_validate(override).model_copy(
        update={"resolved_price_per_slab": resolve_price_per_slab(override)}
    )


@router.post("/custom-materials", response_model=CustomMaterialOut, status_code=status.HTTP_201_CREATED)
def create_custom_material(
    data: CustomMaterialCreate,
    current_user: User = Depends(require_role(UserRole.OWNER, UserRole.STAFF)),
    db: Session = Depends(get_db),
):
    surface, variant = catalogue_service.create_custom_material(db, current_user.tenant_id, data)
    return CustomMaterialOut(
        surface_id=surface.id if surface else None,
        variant_id=variant.id if variant else None,
        canonical_name=data.canonical_name,
        saved_to_catalogue=surface is not None,
    )
