"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP } from "@/lib/utils";
import type { BillingPeriod, Plan } from "@/types/billing";

function annualSavingsLabel(plan: Plan): string | null {
  if (plan.monthly_price_gbp == null || plan.annual_price_gbp == null) return null;
  const monthsFree = 12 - plan.annual_price_gbp / plan.monthly_price_gbp;
  return `Save ${Math.round(monthsFree)} months vs. monthly`;
}

// Sprint 034 (Phase 3) — the Enterprise CTA's destination.
//
// Deliberately not a hardcoded address. A `mailto:` on a public pricing page
// is only useful if the mailbox actually exists; one that bounces loses the
// enquiry silently, and an enterprise enquiry is the most valuable thing on
// this page. So the address is supplied at build time by whoever can confirm
// the mailbox exists, and until then the CTA routes somewhere that always
// works rather than shipping a link nobody has verified.
const SALES_EMAIL = process.env.NEXT_PUBLIC_SALES_EMAIL?.trim() || null;

export default function PricingPage() {
  const router = useRouter();
  const { isAuthenticated, role } = useAuth();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [period, setPeriod] = useState<BillingPeriod>("annual");
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getPlans().then(setPlans).catch(() => setError("Could not load pricing."));
  }, []);

  const canSubscribe = isAuthenticated && role === "Owner";

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
    <div className="mx-auto max-w-4xl">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          GeoCore Pricing
        </h1>
        <p className="mt-2 text-sm text-muted">
          Simple plans that scale with your team. Cancel any time.
        </p>

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
            Annual <span className="ml-1 text-xs opacity-80">(best value)</span>
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
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {plans.map((plan) => {
            const price = period === "monthly" ? plan.monthly_price_gbp : plan.annual_price_gbp;
            const savings = period === "annual" ? annualSavingsLabel(plan) : null;

            return (
              <Card
                key={plan.plan}
                className={plan.annual_recommended && period === "annual" ? "border-accent" : undefined}
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>{plan.name}</CardTitle>
                    {plan.annual_recommended && period === "annual" && (
                      <Badge tone="info">Recommended</Badge>
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
                        : `Up to ${plan.entitlements.seats} team members`}
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
                    {plan.self_service ? (
                      canSubscribe ? (
                        <Button
                          className="w-full"
                          disabled={loadingPlan === plan.plan}
                          onClick={() => handleSubscribe(plan.plan)}
                        >
                          {loadingPlan === plan.plan ? "Redirecting…" : `Choose ${plan.name}`}
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
