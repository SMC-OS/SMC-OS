import type { NextConfig } from "next";

// Sprint 034 (Phase 2) — the public GeoCore site served at the apex
// (geocore.one). Deliberately a separate app from apps/web: the apex must
// be a fast, fully indexable marketing surface, and apps/web's root route
// is the authenticated dashboard, which redirects anonymous visitors to
// /login. Pointing the apex at that app would resolve the root domain to a
// login redirect — nothing for a crawler to index, on the single strongest
// SEO asset the brand owns.
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    // Mirrors apps/web/next.config.ts (Sprint 031, itself mirroring
    // app/core/middleware.py's SecurityHeadersMiddleware). HSTS is added
    // only under APP_ENV=production for the same reason as there: sending
    // it over plain HTTP in development makes browsers cache a forced-HTTPS
    // policy for localhost.
    const headers = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
    ];
    if (process.env.APP_ENV === "production") {
      headers.push({
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains",
      });
    }
    return [{ source: "/:path*", headers }];
  },
};

export default nextConfig;
