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

export const SITE_URL = origin(process.env.NEXT_PUBLIC_SITE_URL, "https://geocore.one");
export const APP_URL = origin(process.env.NEXT_PUBLIC_APP_URL, "https://app.geocore.one");

export const SITE_NAME = "GeoCore";
export const SITE_TAGLINE = "Build smarter together";
export const SITE_DESCRIPTION =
  "GeoCore is the AI operating system for stone and construction businesses — quoting, projects, scheduling and client communication in one place.";

/**
 * Whether this deployment should allow indexing. Only the production
 * canonical host does; every preview and staging host stays out of the
 * index. Guarding this here rather than in robots.ts keeps the same
 * decision available to the page metadata.
 */
export const IS_INDEXABLE =
  process.env.APP_ENV === "production" && SITE_URL === "https://geocore.one";
