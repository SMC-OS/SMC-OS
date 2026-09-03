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
