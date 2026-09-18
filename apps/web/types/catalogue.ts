// Sprint 042 (GeoCore Premium OS Plan 03) — mirrors app/catalogue/models.py.

export const MATERIAL_FAMILIES = [
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
] as const;

export type MaterialFamily = (typeof MATERIAL_FAMILIES)[number];

export const MATERIAL_FAMILY_LABELS: Record<MaterialFamily, string> = {
  quartz: "Quartz",
  granite: "Granite",
  marble: "Marble",
  quartzite: "Quartzite",
  porcelain: "Porcelain",
  ceramic: "Ceramic",
  sintered_stone: "Sintered Stone",
  onyx: "Onyx",
  other_natural_stone: "Other Natural Stone",
  other_engineered_surface: "Other Engineered Surface",
};

export interface SurfaceSearchResult {
  id: string;
  canonical_name: string;
  material_family: MaterialFamily;
  colour_family: string | null;
  supplier_name: string | null;
  manufacturer_name: string | null;
  brand_name: string | null;
  collection_name: string | null;
  active: boolean;
  discontinued: boolean;
  is_tenant_private: boolean;
  thicknesses_mm: number[];
  finishes: string[];
  has_tenant_price: boolean;
}

export interface SurfaceVariant {
  id: string;
  thickness_mm: number | null;
  finish: string | null;
  slab_length_mm: number | null;
  slab_width_mm: number | null;
  supplier_variant_sku: string | null;
  active: boolean;
}

export interface TenantOverride {
  id: string;
  surface_id: string;
  surface_variant_id: string | null;
  preferred_supplier_id: string | null;
  supplier_account_ref: string | null;
  tenant_supplier_sku: string | null;
  buy_cost_per_slab: number | null;
  buy_cost_per_m2: number | null;
  delivery_cost: number | null;
  fabrication_rate: number | null;
  installation_rate: number | null;
  default_markup_percent: number | null;
  target_margin_percent: number | null;
  selling_price_per_slab: number | null;
  selling_price_per_m2: number | null;
  stock_status: string | null;
  lead_time_days: number | null;
  tenant_active: boolean;
  private_notes: string | null;
  resolved_price_per_slab: number | null;
  updated_at: string;
}

export interface TenantOverrideInput {
  surface_variant_id?: string | null;
  buy_cost_per_slab?: number | null;
  default_markup_percent?: number | null;
  target_margin_percent?: number | null;
  selling_price_per_slab?: number | null;
  stock_status?: string | null;
  lead_time_days?: number | null;
  private_notes?: string | null;
}

interface NamedRef {
  id: string;
  name: string;
  slug: string;
}

export interface SurfaceDetail {
  id: string;
  is_tenant_private: boolean;
  canonical_name: string;
  material_family: MaterialFamily;
  colour_family: string | null;
  pattern_family: string | null;
  origin_country: string | null;
  supplier: NamedRef | null;
  manufacturer: NamedRef | null;
  brand: NamedRef | null;
  collection: NamedRef | null;
  supplier_sku: string | null;
  manufacturer_sku: string | null;
  active: boolean;
  discontinued: boolean;
  source_name: string | null;
  source_url: string | null;
  source_verified_at: string | null;
  variants: SurfaceVariant[];
  tenant_override: TenantOverride | null;
}

export interface CustomMaterialInput {
  canonical_name: string;
  supplier_name?: string | null;
  manufacturer_name?: string | null;
  material_family: MaterialFamily;
  variant?: {
    thickness_mm?: number | null;
    finish?: string | null;
    slab_length_mm?: number | null;
    slab_width_mm?: number | null;
  };
  buy_cost_per_slab?: number | null;
  selling_price_per_slab?: number | null;
  default_markup_percent?: number | null;
  save_to_catalogue: boolean;
}

export interface CustomMaterialResult {
  surface_id: string | null;
  variant_id: string | null;
  canonical_name: string;
  saved_to_catalogue: boolean;
}
