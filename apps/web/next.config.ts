import type { NextConfig } from "next";
import { createRequire } from "node:module";
import path from "node:path";

const loadRuntimeConfig = createRequire(__filename);
const { resolveApiBaseUrl } = loadRuntimeConfig(
  path.join(__dirname, "lib", "runtime-config.ts"),
) as typeof import("./lib/runtime-config");

resolveApiBaseUrl();

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    // Sprint 031 — mirrors app/core/middleware.py's SecurityHeadersMiddleware
    // (Sprint 026 Contract C) for the Web response. Strict-Transport-Security
    // is added only when APP_ENV=production, same reasoning as the backend:
    // sending it over plain HTTP in development would make browsers cache a
    // forced-HTTPS policy for localhost. APP_ENV, not NODE_ENV, matches the
    // rest of this project's deployment-intent convention (see
    // lib/runtime-config.ts).
    // Next's development runtime uses eval for source-map diagnostics. Keep
    // that compatibility exception strictly local to development; the
    // production CSP remains free of unsafe-eval.
    const scriptSrc = process.env.APP_ENV === "production"
      ? "'self' 'unsafe-inline'"
      : "'self' 'unsafe-inline' 'unsafe-eval'";
    // The local E2E server deliberately uses a loopback HTTP API. Keep that
    // development-only connection target out of the production CSP.
    const connectSrc = process.env.APP_ENV === "production"
      ? "'self' https:"
      : "'self' https: http://127.0.0.1:8000 http://localhost:8000";
    const headers = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Content-Security-Policy", value: `default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src ${scriptSrc}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src ${connectSrc}` },
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
