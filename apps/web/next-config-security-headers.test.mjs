import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Sprint 031 — Web security response headers. Sprint 026's own contract
// (docs/SPRINTS/sprint-026.md, Contract C) is scoped to the FastAPI
// backend only; this file is the equivalent static contract for the
// Next.js frontend, following the same style as Dockerfile.test.mjs
// (regex-on-source-text, not a runtime render) since next.config.ts's
// headers() function isn't otherwise directly invokable from a test
// without a full Next dev/build server.

const nextConfig = await readFile(new URL("./next.config.ts", import.meta.url), "utf8");

test("next.config.ts declares a headers() function", () => {
  assert.match(nextConfig, /async\s+headers\s*\(\s*\)/);
});

test("security headers apply to every route", () => {
  assert.match(nextConfig, /source:\s*["']\/:path\*["']/);
});

test("Strict-Transport-Security is set with a long max-age and includeSubDomains", () => {
  assert.match(
    nextConfig,
    /Strict-Transport-Security[\s\S]{0,80}max-age=\d{7,}[\s\S]{0,40}includeSubDomains/,
  );
});

test("Strict-Transport-Security is gated to production only, matching the backend's own SecurityHeadersMiddleware reasoning", () => {
  // Sprint 026's backend equivalent (app/core/middleware.py) only adds HSTS
  // when app_env is production, because sending it over plain HTTP in
  // development would make browsers cache a forced-HTTPS policy for
  // localhost. This project's deployment-intent variable is APP_ENV (not
  // Next's own NODE_ENV) — see lib/runtime-config.ts.
  assert.match(nextConfig, /process\.env\.APP_ENV\s*===\s*["']production["']/);
});

test("X-Content-Type-Options is nosniff", () => {
  assert.match(nextConfig, /X-Content-Type-Options[\s\S]{0,40}nosniff/);
});

test("Referrer-Policy is strict-origin-when-cross-origin", () => {
  assert.match(nextConfig, /Referrer-Policy[\s\S]{0,60}strict-origin-when-cross-origin/);
});

test("X-Frame-Options denies framing", () => {
  assert.match(nextConfig, /X-Frame-Options[\s\S]{0,20}DENY/);
});

test("Content-Security-Policy restricts framing only, not script or style", () => {
  assert.match(nextConfig, /Content-Security-Policy[\s\S]{0,60}frame-ancestors 'none'/);
  assert.doesNotMatch(nextConfig, /script-src/);
  assert.doesNotMatch(nextConfig, /style-src/);
});

test("web security-headers contract is reproducibly invoked by package scripts and CI", async () => {
  const packageJson = JSON.parse(
    await readFile(new URL("./package.json", import.meta.url), "utf8"),
  );
  const ci = await readFile(new URL("../../.github/workflows/ci.yml", import.meta.url), "utf8");

  assert.equal(
    packageJson.scripts["test:security-headers"],
    "node --test next-config-security-headers.test.mjs",
  );
  assert.match(ci, /pnpm --filter web test:security-headers/);
});
