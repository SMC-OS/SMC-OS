import type { MetadataRoute } from "next";

/**
 * Sprint 034 (Phase 2) — the application host (app.geocore.one) is not a
 * search surface and must never compete with the marketing site.
 *
 * Every route in this app is behind authentication or is a token-scoped
 * customer link, so there is nothing here a crawler should index, and two
 * concrete harms if it tries: the login page ranking for brand queries
 * ahead of geocore.one, and portal/invite URLs — which are capability
 * tokens, not secrets behind a login — being discovered and archived.
 *
 * Unlike apps/marketing this is unconditional. There is no environment in
 * which indexing the application is correct.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", disallow: "/" }],
  };
}
