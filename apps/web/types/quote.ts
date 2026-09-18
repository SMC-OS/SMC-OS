// Sprint 005: mirrors the seeded catalogue in app/materials/seed.py.
// Materials stay internal (no GET /api/v1/materials this sprint), so this
// list is hand-kept in sync the same way the previous 3-item list was.
export const MATERIAL_OPTIONS = [
  // Quartz
  "Calacatta Gold",
  "Calacatta Oro",
  "Nero Marquina",
  "Statuario White",
  "Carrara Mist",
  // Granite
  "Absolute Black",
  "Kashmir White",
  "Baltic Brown",
  // Marble
  "Carrara White",
  "Emperador Brown",
  "Statuario Marble",
  // Porcelain
  "Grey Concrete Porcelain",
  "Calacatta Porcelain",
  // Dekton
  "Dekton Sirocco",
  "Dekton Kelya",
] as const;

export const THICKNESS_OPTIONS = ["20mm", "30mm"] as const;

export const DIMENSION_UNITS = ["mm", "cm", "m"] as const;
export type DimensionUnit = (typeof DIMENSION_UNITS)[number];

// Sprint 033 (Workstream C) — true multi-line-item quotes. Every item is
// independent: its own material/thickness/quantity/dimensions. A
// worktop, an island, a splashback, and an upstand on the same quote
// never share a dimension.
export const ITEM_TYPES = [
  "worktop",
  "island",
  "splashback",
  "upstand",
  "sill",
  "waterfall_panel",
  "other",
] as const;
export type ItemType = (typeof ITEM_TYPES)[number];

export const ITEM_TYPE_LABELS: Record<ItemType, string> = {
  worktop: "Worktop",
  island: "Island",
  splashback: "Splashback",
  upstand: "Upstand",
  sill: "Window sill",
  waterfall_panel: "Waterfall panel",
  other: "Other",
};

export interface QuoteItemRequest {
  item_type: ItemType;
  material: string;
  thickness: string;
  quantity: number;
  length_mm: number;
  width_mm?: number;
  thickness_mm?: number | null;
  unit_input?: DimensionUnit;
  notes?: string | null;
  // Sprint 042 (GeoCore Premium OS Plan 03) — Stone Quote Engine V2.
  // Optional and additive: when set, the backend prices this item from
  // the Master Catalogue + the caller's own tenant override instead of
  // the free-text material/thickness lookup. `material`/`thickness`
  // above are still sent as the human-readable label either way.
  catalogue_surface_id?: string | null;
  catalogue_variant_id?: string | null;
}

export interface QuoteItem {
  id: string;
  position: number;
  item_type: ItemType;
  // Sprint 036 — "stone" keeps the slab columns below meaningful;
  // "labour"/"material"/"other" are general construction lines described
  // in words, where the slab columns are null.
  line_kind: "stone" | LineKind;
  description: string | null;
  unit: string | null;
  unit_price: number | null;
  material: string | null;
  thickness: string | null;
  quantity: number;
  length_mm: number | null;
  width_mm: number | null;
  thickness_mm: number | null;
  unit_input: string;
  notes: string | null;
  price_per_slab: number | null;
  slabs: number | null;
  line_total: number | null;
  // GeoCore Premium OS Plan 05 (Sprint 044), Task 35 — present only on a
  // stone line created via catalogue selection; lets this line be sent
  // straight to a project's material requirements.
  catalogue_surface_id: string | null;
  catalogue_variant_id: string | null;
}

/** Sprint 033 (Workstream C): `items` is the source of truth — a quote is
 * one or more independent line items. The flat `material`/`thickness`/
 * `length_mm` legacy fields (Sprint 032 and earlier) are still accepted
 * as a convenience alias for a single-item quote; the backend wraps them
 * into a single "worktop" item automatically when `items` isn't given. */
export interface QuoteRequest {
  customer: string;
  postcode?: string;
  items?: QuoteItemRequest[];

  // Legacy single-item alias — omit `items` and use these instead for a
  // simple one-item quote.
  material?: string;
  thickness?: string;
  quantity?: number;
  length_mm?: number;
  width_mm?: number;
  thickness_mm?: number | null;
  unit_input?: DimensionUnit;

  // Sprint 007: optional link to a real customer record. `customer` (free
  // text) stays required — the quotes table has no name column, only this
  // FK, so an unlinked quote's name lives only in the calculated response.
  customer_id?: string | null;
}

export interface QuoteResult {
  customer: string;
  // Best-effort single-item summary (see app/quotes/calculator.py's
  // summarize_items()) — "Multiple materials"/"Mixed" when items disagree.
  material: string;
  thickness: string;
  slabs: number;
  price_per_slab: number | null;
  items: QuoteItem[];
  price_before_vat: number;
  vat: number;
  total: number;
  // Sprint 007: present once the quote is persisted.
  id: string;
  customer_id?: string | null;
  created_at: string;
}

/** AI Quotation Generator — extraction only, never pricing. Every field
 * is optional: incompleteness must be visible, not silently defaulted.
 * Deliberately has no price-shaped field anywhere — the AI never
 * computes money (see docs/DECISIONS.md ADR-024).
 * Sprint 033 (Workstream C): a draft is a list of independent item
 * drafts now, each with its own material_match_status ("found"/
 * "multiple"/"not_found") so the UI can show the same FOUND/MULTIPLE/
 * NOT_FOUND distinction the backend's canonical MaterialSearchService
 * produces per item — never a silent guess. */
export interface AIQuoteItemDraft {
  item_type: ItemType;
  material: string | null;
  material_raw: string | null;
  material_match_status: "found" | "multiple" | "not_found" | null;
  material_candidates: string[];
  thickness: string | null;
  quantity: number | null;
  length_mm: number | null;
  width_mm: number | null;
  thickness_mm: number | null;
  unit_input: string | null;
  warnings: string[];
}

export interface AIQuoteDraft {
  customer: string | null;
  postcode: string | null;
  items: AIQuoteItemDraft[];
  warnings: string[];
}

// Sprint 036 — "sent" joins the lifecycle. Marking a quote as sent
// records that a person gave it to the customer; GeoCore has no email,
// SMS or messaging channel and transmits nothing itself.
export const QUOTE_STATUSES = ["draft", "sent", "approved"] as const;

export type QuoteStatus = (typeof QUOTE_STATUSES)[number];

export const QUOTE_STATUS_LABELS: Record<QuoteStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  approved: "Approved",
};

/* ---------------------------------------------------------------------
   Sprint 036 (Workstream E) — universal quoting.

   A quote is one of two kinds. "stone" is the specialist worktop
   workflow, priced by slab area from the material catalogue, unchanged
   since Sprint 033. "general" is every other kind of construction and
   renovation work, priced as quantity x unit price per line.

   They share a lifecycle (draft -> sent -> approved -> project) and share
   nothing else, which is exactly why the discriminator exists.
--------------------------------------------------------------------- */

export const QUOTE_KINDS = ["general", "stone"] as const;
export type QuoteKind = (typeof QUOTE_KINDS)[number];

export const LINE_KINDS = ["labour", "material", "other"] as const;
export type LineKind = (typeof LINE_KINDS)[number];

export const LINE_KIND_LABELS: Record<LineKind, string> = {
  labour: "Labour",
  material: "Materials",
  other: "Other",
};

/** Served by GET /api/v1/quotes/meta/trades — never duplicated as a
 * frontend constant, so the quote form, the project form and the
 * onboarding picker cannot drift apart. */
export interface Trade {
  key: string;
  label: string;
  default_quote_kind: QuoteKind;
}

/** Served by GET /api/v1/quotes/meta/units. */
export interface QuoteUnit {
  key: string;
  label: string;
}

export interface GeneralQuoteLineRequest {
  line_kind: LineKind;
  description: string;
  quantity: number;
  unit: string;
  unit_price: number;
  notes?: string | null;
}

export interface GeneralQuoteRequest {
  customer_id?: string | null;
  title: string;
  trade?: string | null;
  site_address_line1?: string | null;
  site_address_line2?: string | null;
  site_city?: string | null;
  site_postcode?: string | null;
  scope_of_works?: string | null;
  notes?: string | null;
  exclusions?: string | null;
  terms?: string | null;
  valid_until?: string | null;
  vat_rate?: number;
  discount_amount?: number | null;
  lines: GeneralQuoteLineRequest[];
}

/** PATCH body. Omitting `lines` leaves the existing ones untouched;
 * sending them replaces the set wholesale. */
export type GeneralQuoteUpdate = Partial<GeneralQuoteRequest>;

/** Shape returned by GET /api/v1/quotes and GET /api/v1/quotes/{id} —
 * the persisted row, not the freshly-calculated response. `items` is the
 * source of truth (Sprint 033); the flat fields below stay as a
 * best-effort single-item summary for any older reader. */
export interface Quote {
  id: string;
  customer_id: string | null;

  // --- Sprint 036: the universal quote envelope. ---
  quote_kind: QuoteKind;
  title: string | null;
  trade: string | null;
  site_address_line1: string | null;
  site_address_line2: string | null;
  site_city: string | null;
  site_postcode: string | null;
  scope_of_works: string | null;
  notes: string | null;
  exclusions: string | null;
  terms: string | null;
  valid_until: string | null;
  currency: string;
  vat_rate: number;
  subtotal: number | null;
  discount_amount: number | null;
  sent_at: string | null;

  // --- Stone-only. Null on a general quote. ---
  material: string | null;
  thickness: string | null;
  kitchen_length: number | null;
  quantity?: number;
  length_mm?: number;
  width_mm?: number;
  thickness_mm?: number | null;
  unit_input?: string;
  island: boolean;
  waterfall: number;
  splashback: boolean;
  splashback_length_mm?: number | null;
  upstands: boolean;
  upstands_length_mm?: number | null;
  postcode: string | null;
  price_per_slab: number;
  price_before_vat: number;
  vat: number;
  total: number;
  items: QuoteItem[];
  // Sprint 020 — quote approval (app/quotes/router.py's _serialize()).
  status: QuoteStatus;
  approved_at: string | null;
  approved_by_user_id: string | null;
  created_at: string;
}
