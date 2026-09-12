import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { APP_URL, SITE_DESCRIPTION, SITE_NAME, SITE_TAGLINE, SITE_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: `${SITE_NAME} — ${SITE_TAGLINE}`,
  description: SITE_DESCRIPTION,
  openGraph: {
    images: [`${SITE_URL}/brand/og-image.png`],
  },
};

// Sprint 034 (Phase 2) — interim holding page for geocore.one.
//
// Deliberately a real, indexable page rather than a "coming soon" splash or
// a redirect to the application's login screen. It states what GeoCore is,
// who it is for, and how to reach it, so the apex starts accruing search
// authority from day one instead of from whenever the full marketing site
// ships. Everything here is replaceable without touching the app or the API.
//
// Sprint 035 — the approved brand assets have now been supplied
// (docs/DNS_GEOCORE_ONE.md's Workstream B is unblocked); the header now
// renders the real GeoCore horizontal lockup instead of a text wordmark.

const CAPABILITIES = [
  {
    title: "Quoting and estimating",
    body: "Multi-item quotes with real material and slab calculations, priced consistently every time.",
  },
  {
    title: "Projects and scheduling",
    body: "Approved quotes become projects, with site visits, assignments and status tracked in one place.",
  },
  {
    title: "Client portal",
    body: "Customers follow their own job, read documents and message your team without another login to manage.",
  },
  {
    title: "One workspace per business",
    body: "Your data, your team and your company identity on every document — isolated from every other business on the platform.",
  },
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
      },
    ],
  };

  return (
    <>
      <script
        type="application/ld+json"
        // Static, author-controlled object — no user input reaches this.
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
      />

      <header className="site-header">
        <div className="shell">
          <Link className="wordmark" href="/">
            <Image
              src="/brand/horizontal-logo.png"
              alt={`${SITE_NAME} — ${SITE_TAGLINE}`}
              width={200}
              height={49}
              priority
              // Sprint 039 Production Readiness Defect Gate, Blocker 6 — the
              // source asset is already soft (a raster crop from a
              // flattened brand board, no vector master exists; see
              // docs/SPRINTS/sprint-039.md Sec 14.6). Next.js's optimizer
              // re-encodes at quality 75 by default, compounding that
              // softness with extra lossy compression for no reason. This
              // is a safe mitigation only — it stops making a soft source
              // worse, it does not sharpen, upscale or redraw it.
              quality={100}
            />
          </Link>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="shell">
            <p className="eyebrow">People · Projects · Intelligence</p>
            <h1>The operating system for stone and construction businesses.</h1>
            <hr className="rule" />
            <p>
              GeoCore brings quoting, projects, scheduling and client
              communication into one workspace — so the work that wins jobs
              stops living in spreadsheets, notebooks and inboxes.
            </p>
            <div className="actions">
              <a className="button button--primary" href={`${APP_URL}/signup`}>
                Create a workspace
              </a>
              <a className="button button--secondary" href={`${APP_URL}/login`}>
                Sign in
              </a>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="shell">
            <h2>What GeoCore does</h2>
            <p className="section__lead">
              Built around the way a stone and construction business actually
              runs: enquiry, quote, approval, project, installation, invoice.
            </p>
            <ul className="grid">
              {CAPABILITIES.map((capability) => (
                <li className="card" key={capability.title}>
                  <h3>{capability.title}</h3>
                  <p>{capability.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="shell">
          <p>© {new Date().getFullYear()} GeoCore</p>
          <p>
            The full GeoCore site is on its way. In the meantime the platform
            is live at{" "}
            <a href={APP_URL}>app.geocore.one</a>.
          </p>
        </div>
      </footer>
    </>
  );
}
