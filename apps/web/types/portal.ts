import type { PipelineRole } from "@/types/project";

// Sprint 013 — mirrors app/portal/models.py.

export interface PortalLinkOut {
  id: string;
  tenant_id: string;
  customer_id: string;
  created_by_user_id: string;
  status: string;
  expires_at: string;
  created_at: string;
}

/** Same shape as PortalLinkOut, plus the one-time raw token — only ever
 * returned from the create-link response. */
export interface PortalLinkCreateOut extends PortalLinkOut {
  token: string;
}

/** What an unauthenticated customer sees for one of their projects —
 * `notes` is deliberately excluded (may hold internal staff remarks). */
export interface PortalProjectOut {
  id: string;
  name: string;
  /** Raw stage key from the contractor's own pipeline. */
  status: string;
  /** Sprint 039 — the stage resolved server-side. The portal has no
   * session, so it cannot fetch the tenant's pipeline itself. */
  status_label: string | null;
  status_role: PipelineRole | null;
  created_at: string;
}

/** What an unauthenticated customer sees for one of their quotes — no
 * customer_id or other internal cross-references. */
export interface PortalQuoteOut {
  id: string;
  material: string;
  thickness: string;
  kitchen_length: number;
  price_before_vat: number;
  vat: number;
  total: number;
  created_at: string;
}

/** The full public view for a token — always returned with 200, even for
 * a revoked/expired link (status tells the story; projects/quotes are
 * just empty then). */
export interface PortalPublicOut {
  status: string;
  tenant_name: string;
  customer_name: string;
  expires_at: string;
  projects: PortalProjectOut[];
  quotes: PortalQuoteOut[];
}
