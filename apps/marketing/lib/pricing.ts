import type { Plan } from "@/lib/api";

import plansData from "./plans.json";

/**
 * Phase B — the public site's plan catalogue, bundled at build time so the
 * pricing page is server-rendered, indexable and never empty when the API
 * is briefly unavailable.
 *
 * plans.json is generated from the billing API's own output
 * (GET /billing/plans, backed by app/billing/plans.py, the one pricing
 * authority). tests/test_pricing_drift.py fails CI the moment the two
 * disagree, and also locks the approved figures, so this file can never
 * quietly drift from what Checkout actually charges.
 */
export const PLANS = plansData as Plan[];

export const SELF_SERVICE_PLANS = PLANS.filter((plan) => plan.self_service);

export const TRIAL_DAYS = SELF_SERVICE_PLANS[0]?.trial_days ?? 14;

/** "Starter" rather than "GeoCore Starter" where the brand is already on screen. */
export function shortPlanName(plan: Plan): string {
  return plan.name.replace(/^GeoCore\s+/, "");
}

export function seatsLabel(plan: Plan): string {
  const seats = plan.entitlements.seats;
  if (seats == null) return "Unlimited users";
  return seats === 1 ? "1 user" : `${seats} users`;
}
