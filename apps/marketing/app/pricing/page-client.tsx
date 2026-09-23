"use client";

import { useState } from "react";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { TrialDisclosure } from "@/components/TrialDisclosure";
import type { Plan } from "@/lib/api";
import { PLANS, TRIAL_DAYS } from "@/lib/pricing";
import { APP_URL } from "@/lib/site";

type Period = "monthly" | "annual";

function annualSavingsLabel(plan: Plan): string | null {
  if (plan.monthly_price_gbp == null || plan.annual_price_gbp == null) return null;
  const monthsFree = 12 - plan.annual_price_gbp / plan.monthly_price_gbp;
  return `Save ${Math.round(monthsFree)} months vs. monthly`;
}

// Phase B — plans come from the bundled catalogue (lib/pricing.ts), so
// this page server-renders every plan and price and never depends on the
// API being reachable. tests/test_pricing_drift.py keeps it in step with
// the billing code that Checkout actually charges.
const plans = PLANS;

export function PricingPageClient() {
  const [period, setPeriod] = useState<Period>("monthly");

  return (
    <>
      <Nav />
      <main>
        <section className="section section--tight">
          <div className="shell">
            <p className="eyebrow">Pricing</p>
            <h1>Simple plans that scale with your team</h1>
            <p className="section__lead">
              <strong>{TRIAL_DAYS}-day free trial. No card required.</strong> Every self-service
              plan starts with a free trial of the full product. You only add payment details if
              and when you choose to subscribe.
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
                          Start Free Trial
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
          </div>
        </section>

        <section className="section" id="trial-faq">
          <div className="shell">
            <h2>The 14-day trial, in full</h2>
            <dl className="faq">
              <dt>Do I need a card to start?</dt>
              <dd>
                No. Create your account and your {TRIAL_DAYS}-day free trial starts straight away.
                No card required.
              </dd>
              <dt>What happens after {TRIAL_DAYS} days?</dt>
              <dd>
                Nothing is charged — we never took your card. We&apos;ll remind you before the
                trial ends. To keep using GeoCore, choose a plan and add your payment details;
                your workspace and data stay exactly as you left them.
              </dd>
              <dt>Can I subscribe before the trial ends?</dt>
              <dd>
                Yes. Subscribe any time during the trial and your first payment is taken when the
                trial would have ended, so you never lose free days.
              </dd>
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
