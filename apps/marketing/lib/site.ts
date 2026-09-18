/**
 * Sprint 034 (Phase 2) — single source of truth for the public site's
 * canonical origin and the hosts it links to.
 *
 * Read from the environment rather than hardcoded so a staging deploy
 * advertises its own canonical URL instead of claiming to be production —
 * a staging site emitting `<link rel="canonical" href="https://geocore.one">`
 * invites search engines to index the wrong host, or to treat the real one
 * as duplicated.
 */

function origin(value: string | undefined, fallback: string): string {
  if (!value) return fallback;
  return value.replace(/\/+$/, "");
}

// Sprint 035 — verified live against Railway: a custom domain's target is
// always a CNAME, including at a zone apex, and GoDaddy (the registrar of
// record here, confirmed via its nameservers `ns43.domaincontrol.com` /
// `dns.jomax.net`) does not support CNAME/ALIAS/ANAME at the apex. A bare
// `geocore.one` therefore cannot be a Railway CNAME target directly.
// `www.geocore.one` can (it is a normal subdomain), so the canonical,
// indexed, Railway-hosted host is `www.geocore.one`; the apex uses GoDaddy
// Domain Forwarding (a 301, not DNS-level hosting) to reach it. See
// docs/DNS_GEOCORE_ONE.md §1 for the full record table and rationale.
export const SITE_URL = origin(process.env.NEXT_PUBLIC_SITE_URL, "https://www.geocore.one");
export const APP_URL = origin(process.env.NEXT_PUBLIC_APP_URL, "https://app.geocore.one");

export const SITE_NAME = "GeoCore";
// GeoCore Premium OS Plan 02 (Sprint 041) / Master Spec §25 — the
// positioning is revised from Sprint 039 Blocker 7's "construction and
// renovation businesses in general" (which named no trade at all) to the
// explicit, approved product language: GeoCore is the operating system
// for stone AND construction — stone is a first-class specialist
// vertical, not an afterthought, and construction is a first-class
// platform scope, not the whole identity either. See docs/DECISIONS.md
// ADR-043 for the full reasoning and why the locked positioning test was
// rewritten rather than routed around.
export const SITE_TAGLINE = "The Operating System for Stone & Construction";
export const SITE_DESCRIPTION =
  "GeoCore is the operating system for Stone & Construction businesses — run enquiries, quotes, projects, materials, teams, site operations and profitability from one connected platform.";

/**
 * Whether this deployment should allow indexing. Only the production
 * canonical host does; every preview and staging host stays out of the
 * index. Guarding this here rather than in robots.ts keeps the same
 * decision available to the page metadata.
 */
export const IS_INDEXABLE =
  process.env.APP_ENV === "production" && SITE_URL === "https://www.geocore.one";
