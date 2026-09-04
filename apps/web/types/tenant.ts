// Sprint 034 — a tenant's customer-facing company identity.
//
// Distinct from the platform's own brand: these are the details of the
// business the customer is buying from, and they are what appears on that
// tenant's quotes and invoices. The platform name never appears there.
export interface TenantProfile {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;

  legal_name: string | null;
  trading_name: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  postcode: string | null;
  country: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  website: string | null;
  company_number: string | null;
  // Null is a real answer — not every UK business is VAT-registered.
  vat_number: string | null;
  logo_url: string | null;
  document_footer: string | null;
}

// PATCH body: only the keys actually sent are written server-side, so a
// partial object never blanks the fields it omits.
export type TenantProfileUpdate = Partial<
  Omit<TenantProfile, "id" | "slug" | "status" | "created_at">
>;
