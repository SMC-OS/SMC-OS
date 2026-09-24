import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { TrialDisclosure } from "@/components/TrialDisclosure";
import { PLANS, TRIAL_DAYS, seatsLabel, shortPlanName } from "@/lib/pricing";
import { APP_URL, SITE_NAME, SITE_URL } from "@/lib/site";

import { Faq, type FaqItem } from "./faq";
import { StartTracker, TrackedAnchor, TrackedLink } from "./start-client";
import { StickyCta } from "./sticky-cta";

// /start is a paid-campaign funnel, not an organic landing page: it stays
// out of the index (and out of app/sitemap.ts) so ad traffic never
// cannibalises the canonical site's SEO. The canonical uses the shared
// SITE_URL from lib/site.ts, same as every other absolute marketing URL.
const START_CANONICAL = `${SITE_URL}/start`;

export const metadata: Metadata = {
  title: "GeoCore — Run your stone & construction business from one place",
  description: `GeoCore connects customers, quotes, projects, costs, materials and workflows in one place — built for stone fabricators, worktop companies and construction teams. Start free for ${TRIAL_DAYS} days. No card required.`,
  robots: { index: false, follow: true },
  alternates: { canonical: START_CANONICAL },
  openGraph: {
    title: "GeoCore — Run your stone & construction business from one place",
    description: `Customers, quotes, projects, costs, materials and workflows — one system for stone & construction businesses. ${TRIAL_DAYS}-day free trial, no card required.`,
    url: START_CANONICAL,
    images: [`${SITE_URL}/brand/og-image.png`],
  },
};

const SIGNUP_URL = `${APP_URL}/signup`;
const LOGIN_URL = `${APP_URL}/login`;
const DEMO_URL = "/request-demo";

const ROLES = [
  "Stone fabricators",
  "Worktop companies",
  "Builders",
  "Construction contractors",
  "Electricians",
  "Plumbers",
  "Carpenters",
  "Roofers",
  "Multi-trade contractors",
];

const WORKFLOW_STEPS = [
  "Lead",
  "Quote",
  "Approval",
  "Project",
  "Procurement",
  "Installation",
  "Costs",
  "Completion",
];

const FEATURES = [
  {
    title: "Win and organise more work",
    body: "A CRM built for your trade: customers, enquiries and follow-ups in one place, so no lead slips through the cracks.",
  },
  {
    title: "Quote faster",
    body: "Professional quotes with real material and slab calculations, priced consistently and sent in minutes — not evenings.",
  },
  {
    title: "Control every project",
    body: "Tasks, calendar, documents and photos for every job, visible to the whole team from office to site.",
  },
  {
    title: "Know your numbers",
    body: "Track costs, variations and margins per project, so you can see which jobs actually make money.",
  },
  {
    title: "Automate the admin",
    body: "Follow-ups, status updates and document chasing happen in the background — less time on the laptop, more on the job.",
  },
  {
    title: "Keep everything together",
    body: "Customers, quotes, projects, costs and materials in one system, instead of five disconnected tools.",
  },
];

const OUTCOMES = [
  "Less admin — the repetitive chasing is handled for you.",
  "Faster quoting — from enquiry to sent quote in minutes.",
  "Clearer projects — everyone sees the same plan, from office to site.",
  "Better cost control — margins and variations visible on every job.",
  "One place for the whole operation — no more switching between tools.",
];

const FAQ_ITEMS: FaqItem[] = [
  {
    question: "What is GeoCore?",
    answer:
      "GeoCore is a web-based operating system for stone and construction businesses. It connects your customers, quotes, projects, costs, materials and workflows in one place, so you stop jumping between disconnected software.",
  },
  {
    question: "Who is it built for?",
    answer:
      "Stone fabricators, worktop companies, builders, construction contractors and multi-trade teams — including electricians, plumbers, carpenters and roofers. If you quote jobs and run projects, GeoCore is built for you.",
  },
  {
    question: "Is there a free trial?",
    answer: `Yes. Every new workspace starts with a ${TRIAL_DAYS}-day free trial with full access, so you can run real work through it before deciding.`,
  },
  {
    question: "Do I need a credit card?",
    answer: `No. You can start the ${TRIAL_DAYS}-day trial without entering any payment details — no card required. You only add payment if you choose a plan at the end.`,
  },
  {
    question: "Can I use it for construction as well as stone?",
    answer:
      "Yes. GeoCore was designed around stone fabrication workflows, and the same lead-to-completion system works for general construction and multi-trade businesses too.",
  },
  {
    question: "Can my team use it?",
    answer:
      "Yes. Plans include multiple users — from 1 user on Starter up to 25 on Business — so office staff and site teams can work from the same system.",
  },
  {
    question: "Can I manage quotes and projects together?",
    answer:
      "Yes — that's the point. An approved quote becomes a project with tasks, scheduling, documents, photos and costs attached, so nothing gets re-typed or lost between tools.",
  },
  {
    question: "What happens after my trial?",
    answer: `When the ${TRIAL_DAYS} days are up, nothing is charged — we never took your card. You simply choose the plan that fits your team. Your data stays in your workspace — nothing is deleted when the trial ends.`,
  },
  {
    question: "Can I change plans later?",
    answer:
      "Yes. You can move between plans as your team grows or your needs change.",
  },
  {
    question: "Is it available on mobile, tablet and desktop?",
    answer:
      "Yes. GeoCore is a responsive web app — it runs in the browser on phones, tablets and desktops, with nothing to install.",
  },
];

export default function StartPage() {
  return (
    <div className="start-page">
      <StartTracker />

      <header className="site-header start-header">
        <div className="shell start-header__inner">
          <Link className="wordmark start-header__brand" href="/">
            <Image
              src="/brand/g-mark.png"
              alt={`${SITE_NAME} — back to the main site`}
              width={116}
              height={116}
              priority
            />
            <span className="start-header__name">{SITE_NAME}</span>
          </Link>
          <nav className="start-header__nav" aria-label="Account">
            <TrackedAnchor
              className="start-header__login"
              href={LOGIN_URL}
              event="login_clicked"
              eventProps={{ placement: "header" }}
            >
              Log in
            </TrackedAnchor>
            <TrackedLink
              className="button button--primary start-header__cta"
              href={SIGNUP_URL}
              event="hero_trial_clicked"
              eventProps={{ placement: "header" }}
            >
              Start free
            </TrackedLink>
          </nav>
        </div>
      </header>

      <main>
        {/* S1 — Hero */}
        <section className="start-hero" id="start-hero">
          <div className="shell">
            <h1>Run your stone &amp; construction business from one place.</h1>
            <p className="start-hero__lead">
              GeoCore connects customers, quotes, projects, costs, materials
              and workflows — so you stop jumping between disconnected
              software and get on with the job.
            </p>
            <div className="actions">
              <TrackedLink
                className="button button--primary start-hero__cta"
                href={SIGNUP_URL}
                event="hero_trial_clicked"
                eventProps={{ placement: "hero" }}
              >
                Start free for {TRIAL_DAYS} days
              </TrackedLink>
              <TrackedAnchor
                className="button button--secondary start-hero__demo"
                href={DEMO_URL}
                event="demo_clicked"
                eventProps={{ placement: "hero" }}
              >
                Book a demo
              </TrackedAnchor>
            </div>
            <p className="start-reassurance">
              {TRIAL_DAYS}-day free trial. No card required.
            </p>

            {/*
              Product-neutral brand panel. No product screenshots exist yet
              and fabricated UI (invented figures, job names, metrics) is
              not acceptable on a paid funnel, so the hero visual is a
              typographic brand panel with an abstract workflow motif —
              the stage names are GeoCore's real workflow vocabulary, not
              invented data.
            */}
            <div className="start-brand">
              <Image
                className="start-brand__mark"
                src="/brand/g-mark.png"
                alt=""
                width={116}
                height={116}
              />
              <p className="start-brand__tagline">
                One system, from first enquiry to final invoice.
              </p>
              <ol className="start-brand__path" aria-hidden="true">
                {WORKFLOW_STEPS.map((step) => (
                  <li className="start-brand__path-step" key={step}>
                    <span className="start-brand__path-dot" />
                    <span className="start-brand__path-label">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </section>

        {/* S2 — Roles */}
        <section className="section">
          <div className="shell">
            <h2>Built for stone &amp; construction teams</h2>
            <p className="section__lead">
              Whether you template worktops or run multi-trade projects,
              GeoCore fits the way your business already works.
            </p>
            <ul className="start-chips">
              {ROLES.map((role) => (
                <li className="start-chip" key={role}>
                  {role}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* S3 — Workflow */}
        <section className="section">
          <div className="shell">
            <h2>From enquiry to completion. One system.</h2>
            <p className="section__lead">
              Every job follows the same clear path — and everyone can see
              exactly where it is.
            </p>
            <ol className="start-steps">
              {WORKFLOW_STEPS.map((step, index) => (
                <li className="start-step" key={step}>
                  <span className="start-step__number">{index + 1}</span>
                  <span className="start-step__label">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* S4 — Features */}
        <section className="section">
          <div className="shell">
            <h2>Everything the job needs, in one workspace</h2>
            <p className="section__lead">
              Six reasons teams stop stitching together spreadsheets, inboxes
              and notebooks.
            </p>
            <ul className="grid">
              {FEATURES.map((feature) => (
                <li className="card" key={feature.title}>
                  <h3>{feature.title}</h3>
                  <p>{feature.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* S5 — Product showcase (product-neutral abstract visuals) */}
        <section className="section">
          <div className="shell">
            <h2>See the whole job at a glance</h2>
            <p className="section__lead">
              Quoting, project tracking and the numbers behind every job —
              designed for the trade, not for accountants.
            </p>
            <div className="start-showcase">
              <figure className="start-viz">
                <div
                  className="start-viz__glyph start-viz__glyph--lines"
                  aria-hidden="true"
                >
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <figcaption>
                  <strong>Quote faster.</strong> Real material and slab
                  calculations, priced consistently every time.
                </figcaption>
              </figure>

              <figure className="start-viz">
                <div
                  className="start-viz__glyph start-viz__glyph--dots"
                  aria-hidden="true"
                >
                  <span />
                  <span />
                  <span />
                  <span />
                </div>
                <figcaption>
                  <strong>Project 360.</strong> Tasks, schedule, documents and
                  photos for every job, in one view.
                </figcaption>
              </figure>

              <figure className="start-viz">
                <div
                  className="start-viz__glyph start-viz__glyph--bars"
                  aria-hidden="true"
                >
                  <span />
                  <span />
                  <span />
                </div>
                <figcaption>
                  <strong>Know your numbers.</strong> Costs, variations and
                  margins per project — no end-of-month surprises.
                </figcaption>
              </figure>
            </div>
            <div className="start-showcase__cta">
              <TrackedLink
                className="button button--secondary"
                href={SIGNUP_URL}
                event="showcase_cta_clicked"
              >
                Try it on your next job
              </TrackedLink>
            </div>
          </div>
        </section>

        {/* S6 — Why GeoCore */}
        <section className="section">
          <div className="shell">
            <h2>Why GeoCore</h2>
            <p className="section__lead">
              Not more software to manage — less managing, more building.
            </p>
            <ul className="start-outcomes">
              {OUTCOMES.map((outcome) => (
                <li className="start-outcome" key={outcome}>
                  {outcome}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* S7 — Pricing (same drift-tested catalogue as /pricing) */}
        <section className="section">
          <div className="shell">
            <h2>Simple pricing that scales with your team</h2>
            <p className="section__lead">
              Every plan starts with a {TRIAL_DAYS}-day free trial · No card
              required.
            </p>
            <ul className="start-pricing">
              {PLANS.map((plan) =>
                plan.self_service ? (
                  <li className="start-plan" key={plan.plan}>
                    <h3 className="start-plan__name">{shortPlanName(plan)}</h3>
                    <p className="start-plan__price">
                      £{plan.monthly_price_gbp}
                      <span className="start-plan__per">/mo</span>
                    </p>
                    <p className="start-plan__users">{seatsLabel(plan)}</p>
                    <TrackedLink
                      className="button button--primary start-plan__cta"
                      href={`${SIGNUP_URL}?plan=${plan.plan}`}
                      event="pricing_trial_clicked"
                      eventProps={{ plan: plan.plan }}
                    >
                      Start free
                    </TrackedLink>
                    <TrialDisclosure plan={plan} period="monthly" />
                  </li>
                ) : (
                  <li
                    className="start-plan start-plan--enterprise"
                    key={plan.plan}
                  >
                    <h3 className="start-plan__name">{plan.name}</h3>
                    <p className="start-plan__price">Custom</p>
                    <p className="start-plan__users">
                      Larger teams &amp; multiple branches
                    </p>
                    <TrackedAnchor
                      className="button button--secondary start-plan__cta"
                      href={DEMO_URL}
                      event="demo_clicked"
                      eventProps={{ placement: "pricing_enterprise" }}
                    >
                      Book a demo
                    </TrackedAnchor>
                  </li>
                ),
              )}
            </ul>
          </div>
        </section>

        {/* S8 — FAQ */}
        <section className="section">
          <div className="shell">
            <h2>Frequently asked questions</h2>
            <p className="section__lead">
              Everything you need to know before starting your trial.
            </p>
            <Faq items={FAQ_ITEMS} />
          </div>
        </section>

        {/* S9 — Final CTA */}
        <section className="section start-final">
          <div className="shell">
            <h2>
              Your business shouldn&apos;t need five different systems to run
              one job.
            </h2>
            <p className="section__lead">
              Bring customers, quotes, projects and costs together — and give
              every job one clear path from enquiry to completion.
            </p>
            <div className="actions">
              <TrackedLink
                className="button button--primary start-hero__cta"
                href={SIGNUP_URL}
                event="final_trial_clicked"
              >
                Start free for {TRIAL_DAYS} days
              </TrackedLink>
            </div>
            <p className="start-reassurance">No card required.</p>
          </div>
        </section>
      </main>

      <footer className="site-footer start-footer">
        <div className="shell start-footer__inner">
          <Link className="wordmark" href="/">
            <Image
              src="/brand/horizontal-logo.png"
              alt={SITE_NAME}
              width={140}
              height={34}
            />
          </Link>
          <p>
            © {new Date().getFullYear()} GeoCore ·{" "}
            <Link href="/">geocore.one</Link>
          </p>
        </div>
      </footer>

      <StickyCta />
    </div>
  );
}
