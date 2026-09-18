import type { Metadata } from "next";
import Link from "next/link";

import { Footer } from "@/components/Footer";
import { Nav } from "@/components/Nav";
import { EXAMPLE_WORKFLOWS, TRADES } from "@/lib/trades";
import { APP_URL, SITE_DESCRIPTION, SITE_NAME, SITE_TAGLINE, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `${SITE_NAME} — ${SITE_TAGLINE}`,
  description: SITE_DESCRIPTION,
  alternates: { canonical: "/" },
  openGraph: {
    images: [`${SITE_URL}/brand/og-image.png`],
  },
};

// Sprint 041 — GeoCore Premium OS Plan 02. Replaces the Sprint 034
// interim holding page with the full public homepage the Master Spec
// (§2.2) calls for. Every module below is labelled honestly: "Available"
// only for what is actually live in production today (app/*/router.py
// exists and is reachable); everything else says so plainly rather than
// implying it. See docs/DECISIONS.md ADR-043 for the positioning change
// from the previous "construction and renovation businesses" copy.

const MODULES: { title: string; body: string; status?: "planned" | "coming" }[] = [
  {
    title: "Command Center",
    body: "One business-wide view: pipeline by stage, quoted and approved value, site visits and follow-ups that need attention — across every trade at once.",
  },
  {
    title: "Project 360",
    body: "Every job's single workspace — Overview, Workflow, Schedule, Team, Tasks and Timeline — instead of scattered notes, spreadsheets and inboxes.",
  },
  { title: "Customers", body: "Every enquiry, job and conversation tied to one customer record." },
  {
    title: "Quotes",
    body: "Multi-line quotes for labour, materials and other works — plus a specialist slab calculator for stone.",
  },
  { title: "Projects", body: "Approved quotes become projects automatically, ready to move through their trade's own workflow." },
  {
    title: "Trade Workflows",
    body: "27 trades, each with its own real operational sequence — never one stone-shaped pipeline forced onto every job.",
  },
  { title: "Schedule", body: "Site visits, surveys and key dates tracked against the job they belong to." },
  { title: "Tasks", body: "Project-linked tasks assigned to the right person, with due dates that don't get lost." },
  { title: "Team", body: "Assign the right person to the right job and keep everyone working from the same record." },
  { title: "Automations", body: "Trigger follow-ups and internal notifications from the events already happening in your workspace." },
  { title: "GeoCore AI", body: "AI-assisted quote drafting and project context — grounded in your own data, never inventing figures." },
  { title: "Documents", body: "Upload and store the drawings, approvals and paperwork each project needs." },
  {
    title: "Materials / Procurement",
    body: "Supplier and material tracking for stone and general construction alike.",
    status: "planned",
  },
  {
    title: "Financials / Profitability",
    body: "Contract value, variations, recorded cost and forecast margin in one place.",
    status: "coming",
  },
];

const COMMAND_CENTRE_ROLES = [
  "Leads",
  "Survey",
  "Quoted",
  "Approved",
  "Procurement",
  "Scheduled",
  "In Progress",
  "Inspection",
  "Snagging",
  "Handover",
  "Completed",
  "On Hold",
];

export default function HomePage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITE_URL}/#organization`,
        name: SITE_NAME,
        url: SITE_URL,
        description: SITE_DESCRIPTION,
        logo: `${SITE_URL}/brand/horizontal-logo.png`,
      },
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        publisher: { "@id": `${SITE_URL}/#organization` },
        inLanguage: "en-GB",
      },
      {
        "@type": "SoftwareApplication",
        name: SITE_NAME,
        applicationCategory: "BusinessApplication",
        operatingSystem: "Web",
        description: SITE_DESCRIPTION,
        url: SITE_URL,
        publisher: { "@id": `${SITE_URL}/#organization` },
        offers: [
          { "@type": "Offer", name: "Starter", price: "29", priceCurrency: "GBP" },
          { "@type": "Offer", name: "Team", price: "59", priceCurrency: "GBP" },
          { "@type": "Offer", name: "Pro", price: "99", priceCurrency: "GBP" },
          { "@type": "Offer", name: "Business", price: "199", priceCurrency: "GBP" },
        ],
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />

      <Nav />

      <main>
        {/* 1. Hero */}
        <section className="hero">
          <div className="shell">
            <p className="eyebrow">Stone · Construction · One Platform</p>
            <h1>
              GeoCore
              <br />
              The Operating System for Stone &amp; Construction.
            </h1>
            <hr className="rule" />
            <p>
              Run enquiries, quotes, projects, materials, teams, site operations and
              profitability from one connected platform.
            </p>
            <div className="actions">
              <a className="button button--primary" href="/pricing">
                Start 14-Day Trial
              </a>
              <a className="button button--secondary" href="/request-demo">
                Request a Demo
              </a>
              <a className="button button--tertiary" href="#product">
                Explore GeoCore
              </a>
            </div>
          </div>
        </section>

        {/* 2. Trust / product summary */}
        <section className="section section--tight trust-bar">
          <div className="shell trust-bar__grid">
            <p>Tenant-isolated workspace for every business</p>
            <p>Role-based access and full audit history</p>
            <p>Secure billing via Stripe — card required, £0 due today</p>
          </div>
        </section>

        {/* 3. What GeoCore does */}
        <section className="section" id="product">
          <div className="shell">
            <p className="eyebrow">What&apos;s inside GeoCore</p>
            <h2>The operating system behind every job</h2>
            <p className="section__lead">
              This is the account you&apos;re creating — real modules, honestly labelled. Nothing
              below is advertised as live unless it already is.
            </p>
            <ul className="grid grid--modules">
              {MODULES.map((module) => (
                <li className="card" key={module.title}>
                  <div className="card__header">
                    <h3>{module.title}</h3>
                    {module.status === "planned" && <span className="tag tag--planned">Planned</span>}
                    {module.status === "coming" && (
                      <span className="tag tag--coming">Coming in GeoCore Premium OS</span>
                    )}
                  </div>
                  <p>{module.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 4. Command Center */}
        <section className="section section--alt">
          <div className="shell">
            <p className="eyebrow">Command Center</p>
            <h2>One view across every trade</h2>
            <p className="section__lead">
              A stone job on &ldquo;Fabrication&rdquo; and an electrical job on &ldquo;First
              Fix&rdquo; both count toward the same company-wide &ldquo;In Progress&rdquo; number
              — semantic roles, not raw stage labels, are what the Command Center reports on.
            </p>
            <ul className="pill-row">
              {COMMAND_CENTRE_ROLES.map((role) => (
                <li key={role} className="pill">
                  {role}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 5. Project 360 */}
        <section className="section">
          <div className="shell">
            <p className="eyebrow">Project 360</p>
            <h2>Every job, one workspace</h2>
            <p className="section__lead">
              Open a project and find everything about it — no digging through spreadsheets or
              separate systems.
            </p>
            <ul className="pill-row">
              {["Overview", "Workflow", "Schedule", "Team", "Tasks", "Timeline"].map((tab) => (
                <li key={tab} className="pill">
                  {tab}
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 6. Quotes & Customers */}
        <section className="section section--alt">
          <div className="shell two-col">
            <div>
              <p className="eyebrow">Quotes</p>
              <h2>Quote any job, the same reliable way</h2>
              <p>
                Universal line items — labour, materials, other works, quantity and unit price —
                plus a specialist slab calculator when the job is stone.
              </p>
            </div>
            <div>
              <p className="eyebrow">Customers</p>
              <h2>Every enquiry becomes a real record</h2>
              <p>
                Enquiries convert to customers automatically, so nothing about a job&apos;s history
                gets lost between quote and completion.
              </p>
            </div>
          </div>
        </section>

        {/* 7. Trade Workflows */}
        <section className="section" id="trades">
          <div className="shell">
            <p className="eyebrow">Trade Workflows</p>
            <h2>Each trade gets its own operational workflow.</h2>
            <p className="section__lead">
              27 trades, each with a real stage sequence that matches how that work actually
              happens — never one stone-shaped pipeline forced onto every job.
            </p>
            <div className="workflow-examples">
              {EXAMPLE_WORKFLOWS.map((example) => (
                <div key={example.trade} className="workflow-example">
                  <p className="workflow-example__trade">{example.trade}</p>
                  <ol className="workflow-example__sequence">
                    {example.sequence.map((stage, index) => (
                      <li key={stage}>
                        {stage}
                        {index < example.sequence.length - 1 && (
                          <span aria-hidden="true"> → </span>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* 8. Stone specialist tools */}
        <section className="section section--alt">
          <div className="shell">
            <p className="eyebrow">Stone Specialist Tools</p>
            <h2>Deep stone capability, built in</h2>
            <p className="section__lead">
              Stone is a first-class specialist vertical inside GeoCore, not a separate product.
            </p>
            <ul className="grid">
              <li className="card">
                <h3>Stone quoting</h3>
                <p>Slab-based dimensions, thickness and finish, priced consistently every time.</p>
              </li>
              <li className="card">
                <h3>Worktops, islands &amp; splashbacks</h3>
                <p>The specific product shapes a stone fabricator actually quotes and installs.</p>
              </li>
              <li className="card">
                <h3>Template → Fabrication → QC → Installation</h3>
                <p>A real workflow that follows a stone job from measure to fit, stage by stage.</p>
              </li>
              <li className="card">
                <div className="card__header">
                  <h3>Master Stone Catalogue</h3>
                  <span className="tag tag--coming">Coming in GeoCore Premium OS</span>
                </div>
                <p>A structured, searchable supplier and material catalogue with tenant pricing.</p>
              </li>
            </ul>
          </div>
        </section>

        {/* 9. Construction operations */}
        <section className="section">
          <div className="shell">
            <p className="eyebrow">Construction Operations</p>
            <h2>General construction is first-class, not an afterthought</h2>
            <p className="section__lead">
              General Building, Renovation, Extensions, Roofing, Electrical, Plumbing, Carpentry,
              Bathrooms, Kitchens and Flooring all run on their own real workflow — with quote
              lines that never force stone terminology onto a construction job.
            </p>
            <ul className="pill-row">
              <li className="pill">Labour</li>
              <li className="pill">Materials</li>
              <li className="pill">Other works</li>
              <li className="pill">Quantity</li>
              <li className="pill">Unit price</li>
            </ul>
          </div>
        </section>

        {/* 10. Scheduling / Tasks / Teams */}
        <section className="section section--alt">
          <div className="shell two-col">
            <div>
              <p className="eyebrow">Scheduling &amp; Tasks</p>
              <h2>Site visits and tasks, tied to the job</h2>
              <p>Surveys, installations and key dates tracked against the project they belong to — with tasks assigned to the right person.</p>
            </div>
            <div>
              <p className="eyebrow">Team</p>
              <h2>Everyone working from the same record</h2>
              <p>Assign projects to your team and keep field and office on the same page, in real time.</p>
            </div>
          </div>
        </section>

        {/* 11. Automations */}
        <section className="section">
          <div className="shell">
            <p className="eyebrow">Automations</p>
            <h2>Let the events you already track do the work</h2>
            <p className="section__lead">
              Automations trigger from real workspace events — a quote approved, a stage entered
              — so follow-ups and internal notifications happen without anyone remembering to
              send them.
            </p>
          </div>
        </section>

        {/* 12. Financial / operational visibility */}
        <section className="section section--alt">
          <div className="shell">
            <p className="eyebrow">Financial &amp; Operational Visibility</p>
            <h2>Know what&apos;s quoted, approved and moving</h2>
            <p className="section__lead">
              The Command Center already shows quoted and approved value across your pipeline
              today. Deeper cost tracking, variations and forecast margin are{" "}
              <span className="tag tag--coming">coming in GeoCore Premium OS</span>.
            </p>
          </div>
        </section>

        {/* 13. Supported trades */}
        <section className="section">
          <div className="shell">
            <p className="eyebrow">Supported Trades</p>
            <h2>27 trades, one platform</h2>
            <ul className="trade-tag-list">
              {TRADES.filter((t) => t.key !== "other").map((trade) => (
                <li key={trade.key} className="trade-tag">
                  {trade.label}
                </li>
              ))}
            </ul>
            <p className="trade-tag-list__cta">
              <Link href="/request-demo">Don&apos;t see your trade? Ask us — we&apos;re adding more.</Link>
            </p>
          </div>
        </section>

        {/* 14. Pricing (compact) */}
        <section className="section section--alt" id="pricing">
          <div className="shell">
            <p className="eyebrow">Pricing</p>
            <h2>Starter, Team, Pro, Business — and Enterprise</h2>
            <p className="section__lead">£29 to £199 per month. Every self-service plan includes a 14-day free trial.</p>
            <ul className="pricing-teaser">
              <li>
                <strong>Starter</strong> £29/mo · 1 user
              </li>
              <li>
                <strong>Team</strong> £59/mo · 3 users
              </li>
              <li>
                <strong>Pro</strong> £99/mo · 10 users
              </li>
              <li>
                <strong>Business</strong> £199/mo · 25 users
              </li>
              <li>
                <strong>Enterprise</strong> Custom · Book a demo
              </li>
            </ul>
            <div className="actions">
              <a className="button button--primary" href="/pricing">
                View Full Pricing
              </a>
            </div>
          </div>
        </section>

        {/* 15. 14-day trial explanation */}
        <section className="section" id="how-it-works">
          <div className="shell">
            <p className="eyebrow">The 14-Day Trial</p>
            <h2>No surprises before you add a card</h2>
            <ul className="trial-points">
              <li>14-day free trial on every self-service plan</li>
              <li>£0 due today</li>
              <li>A payment method is required to activate your trial</li>
              <li>Cancel before the trial ends to avoid being charged</li>
              <li>Your first billing date and amount are shown before you confirm</li>
            </ul>
            <div className="actions">
              <a className="button button--primary" href="/pricing">
                Start 14-Day Trial
              </a>
            </div>
          </div>
        </section>

        {/* 16. Request demo */}
        <section className="section section--alt">
          <div className="shell">
            <p className="eyebrow">Not ready for a trial?</p>
            <h2>Request a Demo</h2>
            <p className="section__lead">
              No account and no card required — tell us about your business and we&apos;ll show
              you GeoCore running your own kind of job.
            </p>
            <div className="actions">
              <a className="button button--primary" href="/request-demo">
                Request a Demo
              </a>
            </div>
          </div>
        </section>

        {/* 17. Final CTA */}
        <section className="section final-cta">
          <div className="shell">
            <h2>Run your business from one connected platform.</h2>
            <div className="actions">
              <a className="button button--primary" href="/pricing">
                Start 14-Day Trial
              </a>
              <a className="button button--secondary" href="/request-demo">
                Request a Demo
              </a>
              <a className="button button--secondary" href={`${APP_URL}/login`}>
                Sign In
              </a>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </>
  );
}
