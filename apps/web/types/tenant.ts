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

  // --- Sprint 036 — workspace configuration. ---
  /** Drives every money format in the app and denominates new quotes.
   * GBP is the default, not a hardcoded assumption. */
  currency: string;
  /** Trade keys selected during onboarding, in catalogue order. */
  trades: string[];
  onboarding_completed_at: string | null;
  /** Whether an uploaded logo file exists. The stored filename is never
   * exposed — the file is served by its own authenticated endpoint. */
  has_uploaded_logo: boolean;
}

/**
 * Whether this workspace still needs setting up.
 *
 * `required` is computed, not read from `onboarding_completed_at`: every
 * workspace that existed before Sprint 036 has a null there, and sending
 * an established business back to a setup wizard would be a regression
 * dressed as a feature.
 */
export interface OnboardingState {
  required: boolean;
  completed_at: string | null;
  trades: string[];
  currency: string;
  has_company_identity: boolean;
  has_team_invitations: boolean;
  workspace_has_data: boolean;
}

export interface OnboardingUpdate {
  trades?: string[];
  currency?: string;
  complete?: boolean;
}

// PATCH body: only the keys actually sent are written server-side, so a
// partial object never blanks the fields it omits.
export type TenantProfileUpdate = Partial<
  Omit<
    TenantProfile,
    | "id"
    | "slug"
    | "status"
    | "created_at"
    | "trades"
    | "onboarding_completed_at"
    | "has_uploaded_logo"
  >
>;

/** The currencies GeoCore can actually render correctly, in the UI and on
 * a PDF. Deliberately short — a code the product cannot print would
 * produce documents with bare numbers on them. */
export const SUPPORTED_CURRENCIES = ["GBP", "EUR", "USD"] as const;
export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number];
