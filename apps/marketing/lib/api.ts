/**
 * Sprint 041 — the marketing app's first real API calls (previously a
 * fully static site). Deliberately small and hand-rolled rather than a
 * port of apps/web/lib/api.ts: this app only ever calls two public,
 * unauthenticated endpoints (no JWT, no auth-storage, no 401 handling).
 *
 * Set NEXT_PUBLIC_API_URL in apps/marketing/.env.local to point
 * elsewhere; defaults to the local backend in dev, same convention as
 * apps/web/lib/runtime-config.ts.
 */

const DEVELOPMENT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || DEVELOPMENT_API_BASE_URL;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface PlanEntitlements {
  seats: number | null;
  ai_usage_per_month: number | null;
  automations: number | null;
  integrations: number | null;
  advanced_analytics: boolean;
}

export type PlanId = "starter" | "team" | "pro" | "business" | "enterprise";

export interface Plan {
  plan: PlanId;
  name: string;
  self_service: boolean;
  monthly_price_gbp: number | null;
  annual_price_gbp: number | null;
  annual_recommended: boolean;
  trial_days: number | null;
  entitlements: PlanEntitlements;
}

export async function fetchPlans(): Promise<Plan[]> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/billing/plans`, {
      // The public pricing page is otherwise statically prerendered;
      // this one fetch is always live so a locked-price change on the
      // backend never needs a marketing redeploy to show correctly.
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Could not reach the API to load pricing.", 0);
  }
  if (!res.ok) throw new ApiError(`Failed to load pricing (${res.status})`, res.status);
  return (await res.json()) as Plan[];
}

export interface DemoRequestPayload {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  company_name: string;
  team_size: string;
  trades: string[];
  current_system?: string;
  message?: string;
  preferred_contact_method?: string;
  // Honeypot — left empty by a real visitor, hidden via CSS in the form.
  website?: string;
}

export interface DemoRequestFieldErrors {
  [field: string]: string;
}

export async function submitDemoRequest(payload: DemoRequestPayload): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/demo-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError("Could not reach the API. Check your connection and try again.", 0);
  }

  if (res.status === 429) {
    throw new ApiError("You've already sent a request recently — please wait a moment and try again.", 429);
  }
  if (res.status === 422) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      Array.isArray(body?.detail)
        ? body.detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join(" ")
        : "Please check the form and try again.",
      422
    );
  }
  if (!res.ok) {
    throw new ApiError("Something went wrong submitting your request. Please try again.", res.status);
  }
}
