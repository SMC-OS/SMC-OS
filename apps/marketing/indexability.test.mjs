/**
 * Sprint 034 (Phase 2) — build-time contract for the public site's
 * indexability.
 *
 * The failure this guards against is silent and expensive. `IS_INDEXABLE`
 * in lib/site.ts is evaluated when Next prerenders the page, not when the
 * container serves it, so `robots.txt`, the `<meta name="robots">` tag and
 * the canonical URL are all baked into the image at build time. If
 * `APP_ENV=production` ever stops being set in the builder stage, the
 * production image ships `noindex, nofollow` and `Disallow: /` — the site
 * comes up, every page returns 200, nothing errors, and geocore.one simply
 * never appears in search results.
 *
 * These are static assertions over the source rather than a running build,
 * so they cost nothing in CI and fail on the exact edit that would cause it.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const dockerfile = await readFile(new URL("./Dockerfile", import.meta.url), "utf8");
const nextConfig = await readFile(new URL("./next.config.ts", import.meta.url), "utf8");
const site = await readFile(new URL("./lib/site.ts", import.meta.url), "utf8");
const robots = await readFile(new URL("./app/robots.ts", import.meta.url), "utf8");
const page = await readFile(new URL("./app/page.tsx", import.meta.url), "utf8");

test("builder stage sets APP_ENV=production so the image ships an indexable site", () => {
  // Without this the prerendered robots.txt is "Disallow: /".
  assert.match(dockerfile, /ENV\s+APP_ENV=production/);
});

test("builder stage accepts the canonical site and app origins as build args", () => {
  assert.match(dockerfile, /ARG\s+NEXT_PUBLIC_SITE_URL/);
  assert.match(dockerfile, /ARG\s+NEXT_PUBLIC_APP_URL/);
  assert.match(dockerfile, /ENV[\s\S]*NEXT_PUBLIC_SITE_URL=\$NEXT_PUBLIC_SITE_URL/);
});

test("indexing requires BOTH production mode and the canonical production host", () => {
  // A staging deploy must not advertise itself as indexable, and must not
  // claim geocore.one as its canonical URL.
  assert.match(site, /process\.env\.APP_ENV === "production"/);
  assert.match(site, /SITE_URL === "https:\/\/geocore\.one"/);
});

test("robots.ts disallows everything when the deployment is not indexable", () => {
  assert.match(robots, /if\s*\(!IS_INDEXABLE\)/);
  assert.match(robots, /disallow:\s*["']\/["']/);
});

test("robots.ts advertises the sitemap on the indexable host", () => {
  assert.match(robots, /sitemap:\s*`\$\{SITE_URL\}\/sitemap\.xml`/);
});

test("marketing production build emits the standalone artifact the container runs", () => {
  assert.match(nextConfig, /output:\s*["']standalone["']/);
  assert.match(dockerfile, /["']node["'],\s*["']apps\/marketing\/server\.js["']/);
});

test("marketing production image runs as an unprivileged user", () => {
  assert.match(dockerfile, /ENV\s+HOSTNAME=0\.0\.0\.0/);
  assert.match(dockerfile, /USER\s+nextjs/);
});

test("marketing production image does not copy backend secrets", () => {
  assert.doesNotMatch(dockerfile, /COPY\s+.*\.env/i);
  assert.doesNotMatch(dockerfile, /JWT_SECRET|DATABASE_URL|SEED_ADMIN_PASSWORD/i);
});

test("the apex serves a real page rather than redirecting to the application", () => {
  // A redirect to the application's login screen was explicitly rejected:
  // it gives a crawler nothing to index on the strongest URL the brand
  // owns. Comments are stripped first so prose about the decision cannot
  // satisfy or break the assertion.
  const code = nextConfig.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  assert.doesNotMatch(code, /redirects\s*\(/);
  assert.doesNotMatch(code, /destination\s*:/);

  // And the page has real indexable content of its own.
  assert.match(page, /<h1>/);
  assert.doesNotMatch(page, /redirect\(/);
});
