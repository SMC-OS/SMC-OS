// Sprint 032 (Workstream A) — mirrors app/billing/models.py. Widened from
// 2 self-service plans to 4 in Sprint 039 Production Readiness Defect
// Gate, Blocker 3 (docs/SPRINTS/sprint-039.md §14.3) — do not restore the
// old "pro" | "business"-only union.

export type PlanId = "starter" | "team" | "pro" | "business" | "enterprise";
export type BillingPeriod = "monthly" | "annual";

export interface PlanEntitlements {
  seats: number | null;
  ai_usage_per_month: number | null;
  automations: number | null;
  integrations: number | null;
  advanced_analytics: boolean;
}

export interface Plan {
  plan: PlanId;
  name: string;
  self_service: boolean;
  monthly_price_gbp: number | null;
  annual_price_gbp: number | null;
  annual_recommended: boolean;
  // Sprint 041 — null for Enterprise; TRIAL_LENGTH_DAYS for every
  // self-service plan. Drives the public trial-disclosure component.
  trial_days: number | null;
  entitlements: PlanEntitlements;
}

export type SubscriptionStatus =
  | "active"
  | "trialing"
  | "past_due"
  | "unpaid"
  | "cancelled"
  | "incomplete";

export interface Subscription {
  id: string;
  tenant_id: string;
  plan: PlanId;
  billing_period: BillingPeriod;
  status: SubscriptionStatus;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  // Sprint 039 Blocker 3 — both null for a subscription that was never a
  // trial.
  trial_start: string | null;
  trial_end: string | null;
  created_at: string;
  updated_at: string;
}
