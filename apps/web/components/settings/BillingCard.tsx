"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import type { BillingPeriod, Plan, Subscription } from "@/types/billing";

const STATUS_TONE: Record<string, "info" | "success" | "neutral" | "warning" | "danger"> = {
  active: "success",
  trialing: "info",
  past_due: "warning",
  unpaid: "danger",
  cancelled: "neutral",
  incomplete: "neutral",
};

/**
 * Billing & subscription — Sprint 036, Workstream I.
 *
 * Billing existed before this sprint but was the fourth card down a
 * 483-line settings page. It is now its own section with the plan,
 * status, renewal date, monthly/annual choice and the payment-portal
 * link.
 *
 * What this page will NOT do is fake Stripe. Checkout and the customer
 * portal both return 503 when Stripe is not configured, and that 503 is
 * surfaced as a plain sentence rather than a spinner that never resolves
 * or a "coming soon" that implies the button would otherwise work.
 * Invoices and receipts live inside the Stripe customer portal, so this
 * links there rather than listing invoices GeoCore does not hold.
 */
export function BillingCard() {
  const [subscription, setSubscription] = useState<Subscription | null | undefined>(undefined);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [period, setPeriod] = useState<BillingPeriod>("monthly");

  useEffect(() => {
    api
      .getSubscription()
      .then(setSubscription)
      .catch(() => setError("Could not load your subscription."));
    api.getPlans().then(setPlans).catch(() => {});
  }, []);

  async function run(action: () => Promise<void>, unavailable: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? unavailable
          : err instanceof ApiError && err.status === 403
            ? "Only workspace owners can manage billing."
            : "Something went wrong."
      );
    } finally {
      setBusy(false);
    }
  }

  const currentPlan = plans.find((plan) => plan.plan === subscription?.plan);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Your plan</CardTitle>
          <Link href="/pricing" className="tap-link text-xs font-medium text-accent hover:underline">
            Compare plans
          </Link>
        </CardHeader>

        <CardContent className="pt-4">
          {subscription === undefined && (
            <div className="h-16 animate-pulse rounded-lg bg-surface-hover" />
          )}

          {subscription === null && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-foreground">No plan yet</p>
                <p className="text-sm text-muted">
                  Choose a plan to keep using GeoCore beyond your trial.
                </p>
              </div>
              <Link href="/pricing">
                <Button>Choose a plan</Button>
              </Link>
            </div>
          )}

          {subscription && (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-lg font-semibold text-foreground">
                    {currentPlan?.name ?? subscription.plan}
                  </p>
                  <p className="text-sm text-muted">
                    Billed {subscription.billing_period}
                    {subscription.current_period_end &&
                      ` · renews ${formatDate(subscription.current_period_end)}`}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[subscription.status] ?? "neutral"}>
                  {subscription.status.replace("_", " ")}
                </Badge>
              </div>

              {currentPlan?.entitlements && (
                <dl className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-surface-raised p-4 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-xs text-muted">Seats</dt>
                    <dd className="font-medium text-foreground">
                      {currentPlan.entitlements.seats ?? "Unlimited"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Automations</dt>
                    <dd className="font-medium text-foreground">
                      {currentPlan.entitlements.automations ?? "Unlimited"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">AI requests / month</dt>
                    <dd className="font-medium text-foreground">
                      {currentPlan.entitlements.ai_usage_per_month ?? "Unlimited"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Integrations</dt>
                    <dd className="font-medium text-foreground">
                      {currentPlan.entitlements.integrations ?? "Unlimited"}
                    </dd>
                  </div>
                </dl>
              )}

              {subscription.cancel_at_period_end && (
                <p className="rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
                  Your plan ends on{" "}
                  {subscription.current_period_end
                    ? formatDate(subscription.current_period_end)
                    : "the end of this period"}
                  . You can resume any time before then.
                </p>
              )}

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const { portal_url } = await api.createPortalSession();
                      window.location.assign(portal_url);
                    }, "Card payments aren't switched on for this workspace yet, so there's no billing portal to open.")
                  }
                >
                  Payment method &amp; invoices
                </Button>

                {subscription.cancel_at_period_end ? (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        setSubscription(await api.resumeSubscription());
                      }, "Card payments aren't switched on for this workspace yet.")
                    }
                  >
                    Resume plan
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        setSubscription(await api.cancelSubscriptionAtPeriodEnd());
                      }, "Card payments aren't switched on for this workspace yet.")
                    }
                  >
                    Cancel plan
                  </Button>
                )}
              </div>

              <p className="text-xs text-muted">
                Invoices and receipts are in the payment portal above.
              </p>
            </div>
          )}

          {error && (
            <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
              {error}
            </p>
          )}
        </CardContent>
      </Card>

      {plans.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>Change plan</CardTitle>
            <div className="flex gap-1 rounded-full border border-border p-0.5">
              {(["monthly", "annual"] as BillingPeriod[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setPeriod(option)}
                  aria-pressed={period === option}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors",
                    period === option
                      ? "bg-accent text-accent-foreground"
                      : "text-muted hover:text-foreground"
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
          </CardHeader>

          <CardContent className="pt-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {plans.map((plan) => {
                const price =
                  period === "annual" ? plan.annual_price_gbp : plan.monthly_price_gbp;
                const isCurrent = subscription?.plan === plan.plan;

                return (
                  <div
                    key={plan.plan}
                    className={cn(
                      "flex flex-col gap-3 rounded-xl border p-4",
                      isCurrent ? "border-accent bg-accent-subtle" : "border-border"
                    )}
                  >
                    <div>
                      <p className="text-sm font-semibold text-foreground">{plan.name}</p>
                      <p className="mt-1 text-lg font-semibold text-foreground">
                        {price === null
                          ? "Talk to us"
                          : `£${price.toLocaleString("en-GB")}`}
                        {price !== null && (
                          <span className="text-sm font-normal text-muted">
                            {period === "annual" ? "/year" : "/month"}
                          </span>
                        )}
                      </p>
                    </div>

                    {isCurrent ? (
                      <Badge tone="accent" className="self-start">
                        Current plan
                      </Badge>
                    ) : plan.self_service ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        className="self-start"
                        onClick={() =>
                          run(async () => {
                            const { checkout_url } = await api.createCheckoutSession(
                              plan.plan,
                              period
                            );
                            window.location.assign(checkout_url);
                          }, "Card payments aren't switched on for this workspace yet. Get in touch and we'll set your plan up directly.")
                        }
                      >
                        Choose {plan.name}
                      </Button>
                    ) : (
                      <Link href="/pricing" className="self-start">
                        <Button variant="outline" size="sm">
                          Talk to us
                        </Button>
                      </Link>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
