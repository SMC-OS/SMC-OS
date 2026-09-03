// Sprint 032 (Workstream A) — mirrors app/billing/models.py.

export type PlanId = "pro" | "business" | "enterprise";
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
  created_at: string;
  updated_at: string;
}
