"use client";

import { useEffect, useState } from "react";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { TrialDisclosure } from "@/components/TrialDisclosure";
import { ApiError, fetchPlans, type Plan } from "@/lib/api";
import { APP_URL } from "@/lib/site";

type Period = "monthly" | "annual";

function annualSavingsLabel(plan: Plan): string | null {
  if (plan.monthly_price_gbp == null || plan.annual_price_gbp == null) return null;
  const monthsFree = 12 - plan.annual_price_gbp / plan.monthly_price_gbp;
  return `Save ${Math.round(monthsFree)} months vs. monthly`;
}

export function PricingPageClient() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<Period>("monthly");

  useEffect(() => {
    fetchPlans()
      .then(setPlans)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load pricing.")
      );
  }, []);

  return (
    <>
      <Nav />
      <main>
        <section className="section section--tight">
          <div className="shell">
            <p className="eyebrow">Pricing</p>
            <h1>Simple plans that scale with your team</h1>
            <p className="section__lead">
              Every self-service plan starts with a 14-day free trial. A card is required to
              activate the trial and <strong>£0 is due today</strong> — you&apos;re only charged
              once the trial ends, and you can cancel any time before then.
            </p>

            <div className="period-toggle" role="tablist" aria-label="Billing period">
              <button
                type="button"
                role="tab"
                aria-selected={period === "monthly"}
                className={period === "monthly" ? "is-active" : ""}
                onClick={() => setPeriod("monthly")}
              >
                Monthly
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={period === "annual"}
                className={period === "annual" ? "is-active" : ""}
                onClick={() => setPeriod("annual")}
              >
                Annual <span className="period-toggle__badge">2 months free</span>
              </button>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="shell">
            {error && <p className="form-error">{error}</p>}
            {!plans && !error && <p className="text-muted">Loading plans…</p>}

            {plans && (
              <div className="pricing-grid">
                {plans.map((plan) => {
                  const price = period === "monthly" ? plan.monthly_price_gbp : plan.annual_price_gbp;
                  const savings = period === "annual" ? annualSavingsLabel(plan) : null;

                  return (
                    <article
                      key={plan.plan}
                      className={`pricing-card ${plan.annual_recommended && period === "annual" ? "pricing-card--highlight" : ""}`}
                    >
                      <h2>{plan.name}</h2>

                      {plan.self_service ? (
                        <p className="pricing-card__price">
                          £{price}
                          <span>/{period === "monthly" ? "mo" : "yr"}</span>
                        </p>
                      ) : (
                        <p className="pricing-card__price">Custom</p>
                      )}
                      {savings && <p className="pricing-card__savings">{savings}</p>}

                      <ul className="pricing-card__features">
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
                          {plan.entitlements.advanced_analytics
                            ? "Advanced analytics"
                            : "Standard analytics"}
                        </li>
                      </ul>

                      {plan.self_service ? (
                        <>
                          <a
                            className="button button--primary pricing-card__cta"
                            href={`${APP_URL}/signup?plan=${plan.plan}&billing_period=${period}`}
                          >
                            Start 14-Day Trial
                          </a>
                          <TrialDisclosure plan={plan} period={period} />
                        </>
                      ) : (
                        <a className="button button--secondary pricing-card__cta" href="/request-demo">
                          Request a Demo
                        </a>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        <section className="section" id="trial-faq">
          <div className="shell">
            <h2>The 14-day trial, in full</h2>
            <dl className="faq">
              <dt>Is a card required?</dt>
              <dd>
                Yes. GeoCore&apos;s trial is activated through secure Stripe Checkout, which
                requires a payment method up front. Nothing is charged during the trial.
              </dd>
              <dt>What happens after 14 days?</dt>
              <dd>
                Your subscription converts automatically to the plan you chose, billed at the
                price shown above, unless you cancel before the trial ends.
              </dd>
              <dt>Can I cancel during the trial?</dt>
              <dd>Yes, at any time from your billing settings — you won&apos;t be charged.</dd>
              <dt>Is Enterprise self-service?</dt>
              <dd>
                No — Enterprise pricing is custom.{" "}
                <a href="/request-demo">Request a demo</a> and we&apos;ll put together a plan
                for your team.
              </dd>
            </dl>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
