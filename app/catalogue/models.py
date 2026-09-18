"""Master Materials & Supplier Catalogue schemas (Sprint 042, GeoCore
Premium OS Plan 03). Closed vocabularies validated here at the Pydantic
boundary — plain strings in the database, same no-native-enum
convention as everywhere else in this schema.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MATERIAL_FAMILIES = {
    "quartz",
    "granite",
    "marble",
    "quartzite",
    "porcelain",
    "ceramic",
    "sintered_stone",
    "onyx",
    "other_natural_stone",
    "other_engineered_surface",
}


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    website: str | None
    country: str | None
    active: bool


class ManufacturerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    website: str | None
    country: str | None
    active: bool


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    manufacturer_id: uuid.UUID | None
    name: str
    slug: str
    active: bool


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    brand_id: uuid.UUID | None
    manufacturer_id: uuid.UUID | None
    name: str
    active: bool


class SurfaceVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    thickness_mm: float | None
    finish: str | None
    slab_length_mm: float | None
    slab_width_mm: float | None
    supplier_variant_sku: str | None
    active: bool


class TenantOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    surface_id: uuid.UUID
    surface_variant_id: uuid.UUID | None
    preferred_supplier_id: uuid.UUID | None
    supplier_account_ref: str | None
    tenant_supplier_sku: str | None
    buy_cost_per_slab: float | None
    buy_cost_per_m2: float | None
    delivery_cost: float | None
    fabrication_rate: float | None
    installation_rate: float | None
    default_markup_percent: float | None
    target_margin_percent: float | None
    selling_price_per_slab: float | None
    selling_price_per_m2: float | None
    stock_status: str | None
    lead_time_days: int | None
    tenant_active: bool
    private_notes: str | None
    resolved_price_per_slab: float | None = None
    updated_at: datetime


class TenantOverrideIn(BaseModel):
    """A tenant Owner's own commercial data for one surface (Task 3) —
    every field optional; setting nothing simply leaves the price
    unresolved (Task 8: never fabricated)."""

    surface_variant_id: uuid.UUID | None = None
    preferred_supplier_id: uuid.UUID | None = None
    supplier_account_ref: str | None = None
    tenant_supplier_sku: str | None = None
    buy_cost_per_slab: float | None = Field(default=None, ge=0)
    buy_cost_per_m2: float | None = Field(default=None, ge=0)
    delivery_cost: float | None = Field(default=None, ge=0)
    fabrication_rate: float | None = Field(default=None, ge=0)
    installation_rate: float | None = Field(default=None, ge=0)
    default_markup_percent: float | None = Field(default=None, ge=0)
    target_margin_percent: float | None = Field(default=None, ge=0, lt=100)
    selling_price_per_slab: float | None = Field(default=None, ge=0)
    selling_price_per_m2: float | None = Field(default=None, ge=0)
    stock_status: str | None = None
    lead_time_days: int | None = Field(default=None, ge=0)
    tenant_active: bool = True
    private_notes: str | None = None


class SurfaceSearchResult(BaseModel):
    """Concise result data for catalogue search / quote selection (Task
    4) — never the entire row, and never a price (Task 3/8: price is
    resolved separately, per-tenant, from the caller's own override)."""

    id: uuid.UUID
    canonical_name: str
    material_family: str
    colour_family: str | None
    supplier_name: str | None
    manufacturer_name: str | None
    brand_name: str | None
    collection_name: str | None
    active: bool
    discontinued: bool
    is_tenant_private: bool
    thicknesses_mm: list[float]
    finishes: list[str]
    has_tenant_price: bool


class SurfaceDetailOut(BaseModel):
    """Task 15 — global reference data and tenant commercial data kept
    visibly distinct; `tenant_override` is None (never another
    tenant's, never a fabricated one) when nothing has been set."""

    id: uuid.UUID
    is_tenant_private: bool
    canonical_name: str
    material_family: str
    colour_family: str | None
    pattern_family: str | None
    origin_country: str | None
    supplier: SupplierOut | None
    manufacturer: ManufacturerOut | None
    brand: BrandOut | None
    collection: CollectionOut | None
    supplier_sku: str | None
    manufacturer_sku: str | None
    active: bool
    discontinued: bool
    source_name: str | None
    source_url: str | None
    source_verified_at: datetime | None
    variants: list[SurfaceVariantOut]
    tenant_override: TenantOverrideOut | None


class CustomMaterialVariantIn(BaseModel):
    thickness_mm: float | None = Field(default=None, gt=0)
    finish: str | None = None
    slab_length_mm: float | None = Field(default=None, gt=0)
    slab_width_mm: float | None = Field(default=None, gt=0)


class CustomMaterialCreate(BaseModel):
    """Task 9 — the "Can't find your stone? Add custom material" fallback.
    `save_to_catalogue=False` (default) means the material is used for
    the current quote only and is never persisted as a reusable
    CatalogueSurface row — it only ever lives in that quote line's own
    immutable snapshot. `save_to_catalogue=True` persists a real,
    tenant-private CatalogueSurface (never global, never visible to any
    other tenant, never auto-promoted)."""

    canonical_name: str = Field(min_length=1, max_length=200)
    supplier_name: str | None = Field(default=None, max_length=200)
    manufacturer_name: str | None = Field(default=None, max_length=200)
    material_family: str
    variant: CustomMaterialVariantIn = CustomMaterialVariantIn()
    buy_cost_per_slab: float | None = Field(default=None, ge=0)
    selling_price_per_slab: float | None = Field(default=None, ge=0)
    default_markup_percent: float | None = Field(default=None, ge=0)
    save_to_catalogue: bool = False

    @field_validator("material_family")
    @classmethod
    def _family_must_be_known(cls, value: str) -> str:
        if value not in MATERIAL_FAMILIES:
            raise ValueError(f"material_family must be one of {sorted(MATERIAL_FAMILIES)}")
        return value


class CustomMaterialOut(BaseModel):
    surface_id: uuid.UUID | None
    variant_id: uuid.UUID | None
    canonical_name: str
    saved_to_catalogue: bool
