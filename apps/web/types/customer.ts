import type { PipelineRole } from "@/types/project";

export const CUSTOMER_TYPES = ["individual", "company"] as const;
export type CustomerType = (typeof CUSTOMER_TYPES)[number];

export const CUSTOMER_TYPE_LABELS: Record<CustomerType, string> = {
  individual: "Individual",
  company: "Company",
};

/**
 * Sprint 036 (Workstream D) — a construction customer record rather than
 * a contact. `name` stays the only required field and is still the person
 * you actually deal with, even on a commercial job: `company_name` is the
 * organisation, `name` is whoever answers the phone. Collapsing the two
 * would lose the contact on every commercial project.
 */
export interface CustomerCreate {
  name: string;
  email?: string | null;
  phone?: string | null;
  customer_type?: CustomerType;
  company_name?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  postcode?: string | null;
  notes?: string | null;
}

/** PATCH body: an omitted key is left alone, an explicit null clears. */
export type CustomerUpdate = Partial<CustomerCreate>;

export interface Customer extends CustomerCreate {
  id: string;
  customer_type: CustomerType;
  created_at: string;
}

export interface CustomerQuoteSummary {
  id: string;
  quote_kind: string;
  title: string | null;
  trade: string | null;
  status: string;
  currency: string;
  total: number | null;
  valid_until: string | null;
  created_at: string;
}

export interface CustomerProjectSummary {
  id: string;
  name: string;
  status: string;
  // Sprint 039 — resolved server-side against the tenant's pipeline, so
  // this panel needs no second round trip to render a job's stage.
  status_label: string | null;
  status_role: PipelineRole | null;
  project_type: string | null;
  start_date: string | null;
  target_completion_date: string | null;
  estimated_value: number | null;
  created_at: string;
}

/**
 * One call backing the customer detail page's business context.
 *
 * `quoted_value` and `approved_value` are prices offered or committed to,
 * never recognised revenue — the same distinction the dashboard has drawn
 * since Sprint 025, named the same way here so no reader mistakes one for
 * the other.
 */
export interface CustomerContext {
  customer: Customer;
  quotes: CustomerQuoteSummary[];
  projects: CustomerProjectSummary[];
  quoted_value: number;
  approved_value: number;
  open_projects: number;
}
