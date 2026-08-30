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

export interface QuoteRequest {
  customer: string;
  material: string;
  thickness: string;
  kitchen_length: number;
  island: boolean;
  waterfall: number;
  splashback: boolean;
  upstands: boolean;
  postcode?: string;
  // Sprint 007: optional link to a real customer record. `customer` (free
  // text) stays required — the quotes table has no name column, only this
  // FK, so an unlinked quote's name lives only in the calculated response.
  customer_id?: string | null;
}

export interface QuoteResult {
  customer: string;
  material: string;
  slabs: number;
  price_per_slab: number;
  price_before_vat: number;
  vat: number;
  total: number;
  // Sprint 007: present once the quote is persisted.
  id: string;
  customer_id?: string | null;
  created_at: string;
}

/** AI Quotation Generator v1 — extraction only, never pricing. Every
 * field is optional except the boolean/int flags: incompleteness must be
 * visible, not silently defaulted. Deliberately has no price-shaped field
 * anywhere — the AI never computes money (see docs/DECISIONS.md ADR-024). */
export interface AIQuoteDraft {
  customer: string | null;
  material: string | null;
  material_raw: string | null;
  thickness: string | null;
  kitchen_length: number | null;
  island: boolean;
  waterfall: number;
  splashback: boolean;
  upstands: boolean;
  postcode: string | null;
  warnings: string[];
}

// Sprint 020: mirrors the two values app/database/models.py's Quote.status
// column and app/quotes/service.py's approve()/handoff() actually use.
export const QUOTE_STATUSES = ["draft", "approved"] as const;

export type QuoteStatus = (typeof QUOTE_STATUSES)[number];

/** Shape returned by GET /api/v1/quotes and GET /api/v1/quotes/{id} —
 * the persisted row, not the freshly-calculated response (no `customer`
 * name or `slabs`, since neither is a column on `quotes`). */
export interface Quote {
  id: string;
  customer_id: string | null;
  material: string;
  thickness: string;
  kitchen_length: number;
  island: boolean;
  waterfall: number;
  splashback: boolean;
  upstands: boolean;
  postcode: string | null;
  price_per_slab: number;
  price_before_vat: number;
  vat: number;
  total: number;
  // Sprint 020 — quote approval (app/quotes/router.py's _serialize()).
  status: QuoteStatus;
  approved_at: string | null;
  approved_by_user_id: string | null;
  created_at: string;
}
