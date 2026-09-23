import type { Plan } from "@/lib/api";

function amountFor(plan: Plan, period: "monthly" | "annual"): number | null {
  return period === "monthly" ? plan.monthly_price_gbp : plan.annual_price_gbp;
}

/**
 * Phase B — the reusable trial disclosure. GeoCore's trial needs no card,
 * so this says exactly that, and what happens next: nothing is charged
 * automatically, because no payment details exist until the customer
 * chooses to subscribe. Every figure comes from the plan data (trial
 * length and price), never a literal of this component's own.
 */
export function TrialDisclosure({ plan, period }: { plan: Plan; period: "monthly" | "annual" }) {
  if (plan.trial_days == null) return null;
  const amount = amountFor(plan, period);
  if (amount == null) return null;

  return (
    <div className="trial-disclosure">
      <p className="trial-disclosure__headline">
        {plan.trial_days}-day free trial. No card required.
      </p>
      <p>
        Nothing is charged when your trial ends. To keep going, choose this plan at{" "}
        <strong>
          £{amount}/{period === "monthly" ? "month" : "year"}
        </strong>{" "}
        and add your payment details then.
      </p>
    </div>
  );
}
