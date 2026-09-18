import type { Plan } from "@/lib/api";

function firstBillingDate(trialDays: number): string {
  const date = new Date();
  date.setDate(date.getDate() + trialDays);
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

function amountFor(plan: Plan, period: "monthly" | "annual"): number | null {
  return period === "monthly" ? plan.monthly_price_gbp : plan.annual_price_gbp;
}

/**
 * Sprint 041, Task 9 — the reusable trial-disclosure component. Renders
 * before any card-collection step, so a visitor is never surprised by
 * the card requirement. Every figure here is real: `trial_days` and the
 * price both come from GET /billing/plans (app/billing/plans.py's own
 * TRIAL_LENGTH_DAYS and PRICING_GBP — the same constants Stripe Checkout
 * itself uses), never a hard-coded marketing date or amount. The first
 * billing date is "today + trial_days," computed client-side from that
 * real trial length — this is exactly what Stripe's own
 * `trial_period_days` will compute at Checkout, not a guess.
 */
export function TrialDisclosure({ plan, period }: { plan: Plan; period: "monthly" | "annual" }) {
  if (plan.trial_days == null) return null;
  const amount = amountFor(plan, period);
  if (amount == null) return null;

  return (
    <div className="trial-disclosure">
      <p className="trial-disclosure__headline">{plan.trial_days}-day free trial</p>
      <p>
        <strong>£0 due today.</strong> A payment method is required to activate your trial.
      </p>
      <p>
        Your first payment of <strong>£{amount}</strong> will be charged on{" "}
        <strong>{firstBillingDate(plan.trial_days)}</strong> if you don&apos;t cancel before the
        trial ends.
      </p>
    </div>
  );
}
