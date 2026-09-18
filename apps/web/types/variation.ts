/** GeoCore Premium OS Plan 04 (Sprint 043) — mirrors app/variations/models.py.
 * draft: fully editable. sent: items/title locked, may be approved/
 * rejected/voided. approved/rejected/void: terminal — a correction is a
 * new, separate variation, never a rewrite of this one. */

export const VARIATION_STATUSES = ["draft", "sent", "approved", "rejected", "void"] as const;
export type VariationStatus = (typeof VARIATION_STATUSES)[number];

export const VARIATION_STATUS_LABELS: Record<VariationStatus, string> = {
  draft: "Draft",
  sent: "Sent",
  approved: "Approved",
  rejected: "Rejected",
  void: "Void",
};

export const VARIATION_STATUS_TONE: Record<
  VariationStatus,
  "neutral" | "info" | "success" | "danger"
> = {
  draft: "neutral",
  sent: "info",
  approved: "success",
  rejected: "danger",
  void: "neutral",
};

export interface VariationItemIn {
  description: string;
  quantity: number;
  unit: string;
  unit_price: number;
}

export interface VariationItemOut {
  id: string;
  description: string;
  quantity: number;
  unit: string;
  unit_price: number;
  line_total: number;
}

export interface VariationCreate {
  title: string;
  description?: string | null;
  requested_by?: string | null;
  vat_rate?: number;
  items?: VariationItemIn[];
}

/** Draft-only server-side — a sent/approved/rejected/void variation
 * rejects a PATCH with 409. */
export interface VariationUpdate {
  title?: string;
  description?: string | null;
  requested_by?: string | null;
  vat_rate?: number;
  items?: VariationItemIn[];
}

export interface Variation {
  id: string;
  project_id: string;
  reference: string;
  title: string;
  description: string | null;
  status: VariationStatus;
  vat_rate: number;
  subtotal: number;
  vat: number;
  total: number;
  requested_by: string | null;
  approved_at: string | null;
  approved_by_user_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  items: VariationItemOut[];
}
