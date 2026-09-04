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
}

export interface QuoteItem {
  id: string;
  position: number;
  item_type: ItemType;
  material: string;
  thickness: string;
  quantity: number;
  length_mm: number;
  width_mm: number;
  thickness_mm: number | null;
  unit_input: string;
  notes: string | null;
  price_per_slab: number | null;
  slabs: number | null;
  line_total: number | null;
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

// Sprint 020: mirrors the two values app/database/models.py's Quote.status
// column and app/quotes/service.py's approve()/handoff() actually use.
export const QUOTE_STATUSES = ["draft", "approved"] as const;

export type QuoteStatus = (typeof QUOTE_STATUSES)[number];

/** Shape returned by GET /api/v1/quotes and GET /api/v1/quotes/{id} —
 * the persisted row, not the freshly-calculated response. `items` is the
 * source of truth (Sprint 033); the flat fields below stay as a
 * best-effort single-item summary for any older reader. */
export interface Quote {
  id: string;
  customer_id: string | null;
  material: string;
  thickness: string;
  kitchen_length: number;
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
