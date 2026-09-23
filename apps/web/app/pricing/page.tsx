"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP } from "@/lib/utils";
import type { BillingPeriod, Plan, Subscription } from "@/types/billing";

function annualSavingsLabel(plan: Plan): string | null {
  if (plan.monthly_price_gbp == null || plan.annual_price_gbp == null) return null;
  const monthsFree = 12 - plan.annual_price_gbp / plan.monthly_price_gbp;
  return `Save ${Math.round(monthsFree)} months vs. monthly`;
}

function daysRemaining(trialEnd: string): number {
  const ms = new Date(trialEnd).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

function dayLabel(days: number): string {
  return days === 1 ? "1 day" : `${days} days`;
}

// Sprint 034 (Phase 3) — the Enterprise CTA's fallback destination.
//
// Deliberately not a hardcoded address. A `mailto:` on a public pricing page
// is only useful if the mailbox actually exists; one that bounces loses the
// enquiry silently, and an enterprise enquiry is the most valuable thing on
// this page. So the address is supplied at build time by whoever can confirm
// the mailbox exists, and until then the CTA routes somewhere that always
// works rather than shipping a link nobody has verified.
const SALES_EMAIL = process.env.NEXT_PUBLIC_SALES_EMAIL?.trim() || null;

// Sprint 039 Production Readiness Defect Gate, Blocker 3 — Enterprise's
// primary CTA is "Book a demo," not self-service checkout (the locked
// contract explicitly says do not route Enterprise through Checkout).
// Same "no unverified hardcoded destination" reasoning as SALES_EMAIL
// above: no booking provider is hardcoded here, the URL is whatever the
// owner configures (Microsoft Bookings or otherwise — see
// docs/SPRINTS/sprint-039.md §14.3).
const DEMO_BOOKING_URL = process.env.NEXT_PUBLIC_DEMO_BOOKING_URL?.trim() || null;

export default function PricingPage() {
  const router = useRouter();
  const { isAuthenticated, role, billingAccessRequired, refreshAccess } = useAuth();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [period, setPeriod] = useState<BillingPeriod>("annual");
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subscriptionLoaded, setSubscriptionLoaded] = useState(false);
  const [startingTrial, setStartingTrial] = useState(false);

  useEffect(() => {
    api.getPlans().then(setPlans).catch(() => setError("Could not load pricing."));
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    api
      .getSubscription()
      .then((sub) => {
        setSubscription(sub);
        // Phase B — show the period this workspace already chose (on
        // the public pricing page, carried through signup) rather than
        // making them pick it again.
        if (sub?.billing_period) setPeriod(sub.billing_period);
      })
      .catch(() => {})
      .finally(() => setSubscriptionLoaded(true));
  }, [isAuthenticated]);

  const canSubscribe = isAuthenticated && role === "Owner";
  // Phase B — GeoCore's own no-card trial carries trial_state; a
  // Stripe-managed trial (legacy card-required signups) does not.
  const trialState = subscription?.trial_state ?? null;
  const isNoCardTrial = trialState != null;
  const isTrialing = subscription?.status === "trialing";
  // A workspace created before the no-card trial, which never completed
  // the old card checkout, has no subscription at all: it may start its
  // one free trial here.
  const canStartTrial = canSubscribe && subscriptionLoaded && subscription === null && billingAccessRequired;

  async function handleStartTrial() {
    setError(null);
    setStartingTrial(true);
    try {
      const started = await api.startTrial();
      setSubscription(started);
      await refreshAccess();
      router.push("/onboarding");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setStartingTrial(false);
    }
  }

  async function handleSubscribe(planId: string) {
    setError(null);
    setLoadingPlan(planId);
    try {
      const { checkout_url } = await api.createCheckoutSession(
        planId as Plan["plan"],
        period
      );
      window.location.assign(checkout_url);
    } catch (err) {
      // Sprint 039 Blocker 3 — this message is the honest, correct
      // behavior while Stripe genuinely isn't configured yet (a real
      // owner-gate, not a bug to hide behind optimistic UI). It is not
      // shown once Stripe is actually configured, since the checkout
      // call then succeeds instead of returning 503.
      setError(
        err instanceof ApiError && err.status === 503
          ? "Billing isn't fully configured yet — contact your administrator."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong."
      );
    } finally {
      setLoadingPlan(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          GeoCore Pricing
        </h1>
        <p className="mt-2 text-sm text-muted">
          Simple plans that scale with your team. 14-day free trial. No card required.
          You only add payment details when you choose a plan.
        </p>

        {trialState === "active" || trialState === "ending_soon" ? (
          <div
            className={`mx-auto mt-4 max-w-xl rounded-lg px-4 py-3 text-sm ${
              trialState === "ending_soon" ? "bg-warning/10 text-warning" : "bg-info/10 text-info"
            }`}
            role="status"
          >
            <p className="font-medium">
              {dayLabel(subscription?.trial_days_remaining ?? 0)} left in your free trial
            </p>
            <p className="mt-0.5">
              Subscribe any time — you won&apos;t be charged until your trial ends.
            </p>
          </div>
        ) : trialState === "expired" ? (
          <div className="mx-auto mt-4 max-w-xl rounded-lg bg-danger/10 px-4 py-3 text-sm text-danger" role="status">
            <p className="font-medium">Your 14-day free trial has ended.</p>
            <p className="mt-0.5">
              Choose a plan to continue. Your workspace and data are safe — nothing has been deleted.
            </p>
          </div>
        ) : isTrialing && subscription?.trial_end ? (
          // A Stripe-managed trial from the earlier card-required signup
          // flow: Stripe converts it itself, so just show the countdown.
          <p className="mx-auto mt-4 inline-block rounded-full bg-info/10 px-4 py-1.5 text-sm font-medium text-info">
            {dayLabel(daysRemaining(subscription.trial_end))} left in your trial
          </p>
        ) : null}

        {canStartTrial && (
          <div className="mx-auto mt-6 max-w-xl rounded-lg border border-border bg-surface px-4 py-4 text-sm">
            <p className="font-medium text-foreground">Start your 14-day free trial</p>
            <p className="mt-1 text-muted">No card required. Nothing is charged when the trial ends.</p>
            <Button className="mt-3" onClick={handleStartTrial} disabled={startingTrial}>
              {startingTrial ? "Starting your trial…" : "Start free trial"}
            </Button>
          </div>
        )}

        <div className="mt-6 inline-flex items-center gap-1 rounded-full border border-border bg-surface p-1">
          <button
            type="button"
            onClick={() => setPeriod("monthly")}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              period === "monthly"
                ? "bg-accent text-accent-foreground"
                : "text-muted hover:text-foreground"
            }`}
          >
            Monthly
          </button>
          <button
            type="button"
            onClick={() => setPeriod("annual")}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              period === "annual"
                ? "bg-accent text-accent-foreground"
                : "text-muted hover:text-foreground"
            }`}
          >
            Annual <span className="ml-1 text-xs opacity-80">(2 months free)</span>
          </button>
        </div>
      </div>

      {error && (
        <p className="mb-6 rounded-lg bg-danger/10 px-3 py-2 text-center text-sm text-danger">
          {error}
        </p>
      )}

      {!plans && !error && <p className="text-center text-sm text-muted">Loading plans…</p>}

      {plans && (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-5">
          {plans.map((plan) => {
            const price = period === "monthly" ? plan.monthly_price_gbp : plan.annual_price_gbp;
            const savings = period === "annual" ? annualSavingsLabel(plan) : null;
            const isCurrentPlan = subscription != null && subscription.plan === plan.plan;

            return (
              <Card
                key={plan.plan}
                className={
                  isCurrentPlan
                    ? "border-success"
                    : plan.annual_recommended && period === "annual"
                      ? "border-accent"
                      : undefined
                }
              >
                <CardHeader>
                  <div className="flex items-center justify-between gap-2">
                    <CardTitle>{plan.name}</CardTitle>
                    {isCurrentPlan ? (
                      <Badge tone="success">{isTrialing ? "Your trial" : "Current plan"}</Badge>
                    ) : (
                      plan.annual_recommended &&
                      period === "annual" && <Badge tone="info">2 months free</Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="pt-4">
                  {plan.self_service ? (
                    <>
                      <p className="text-3xl font-semibold text-foreground">
                        {formatCurrencyGBP(price ?? 0)}
                        <span className="text-sm font-normal text-muted">
                          /{period === "monthly" ? "mo" : "yr"}
                        </span>
                      </p>
                      {savings && (
                        <p className="mt-1 text-sm font-medium text-success">{savings}</p>
                      )}
                    </>
                  ) : (
                    <p className="text-3xl font-semibold text-foreground">Custom</p>
                  )}

                  <ul className="mt-4 flex flex-col gap-2 text-sm text-foreground">
                    <li>
                      {plan.entitlements.seats == null
                        ? "Unlimited seats"
                        : plan.entitlements.seats === 1
                          ? "1 included user"
                          : `${plan.entitlements.seats} included users`}
                    </li>
                    <li>
                      {plan.entitlements.ai_usage_per_month == null
                        ? "Unlimited AI usage"
                        : `${plan.entitlements.ai_usage_per_month.toLocaleString()} AI requests/month`}
                    </li>
                    <li>
                      {plan.entitlements.automations == null
                        ? "Unlimited automations"
                        : `${plan.entitlements.automations} automations`}
                    </li>
                    <li>
                      {plan.entitlements.integrations == null
                        ? "Unlimited integrations"
                        : `${plan.entitlements.integrations} integrations`}
                    </li>
                    <li>
                      {plan.entitlements.advanced_analytics
                        ? "Advanced analytics"
                        : "Standard analytics"}
                    </li>
                  </ul>

                  <div className="mt-6">
                    {isCurrentPlan && !isNoCardTrial ? (
                      <Button className="w-full" variant="outline" disabled>
                        {isTrialing ? "Trialing this plan" : "Current plan"}
                      </Button>
                    ) : plan.self_service ? (
                      canSubscribe ? (
                        <Button
                          className="w-full"
                          disabled={loadingPlan === plan.plan}
                          onClick={() => handleSubscribe(plan.plan)}
                        >
                          {loadingPlan === plan.plan
                            ? "Redirecting…"
                            : isNoCardTrial
                              ? `Subscribe to ${plan.name}`
                              : isTrialing
                                ? `Upgrade to ${plan.name}`
                                : `Choose ${plan.name}`}
                        </Button>
                      ) : isAuthenticated ? (
                        <p className="text-center text-xs text-muted">
                          Ask your workspace owner to upgrade.
                        </p>
                      ) : (
                        <Button
                          className="w-full"
                          variant="outline"
                          onClick={() => router.push("/login")}
                        >
                          Sign in to subscribe
                        </Button>
                      )
                    ) : DEMO_BOOKING_URL ? (
                      <a
                        href={DEMO_BOOKING_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-border px-4 text-sm font-medium text-foreground transition-colors hover:bg-surface-hover"
                      >
                        Book a demo
                      </a>
                    ) : SALES_EMAIL ? (
                      <a
                        href={`mailto:${SALES_EMAIL}?subject=GeoCore%20Enterprise`}
                        className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-border px-4 text-sm font-medium text-foreground transition-colors hover:bg-surface-hover"
                      >
                        Contact sales
                      </a>
                    ) : (
                      <Button
                        className="w-full"
                        variant="outline"
                        onClick={() => router.push("/signup")}
                      >
                        Get started
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
