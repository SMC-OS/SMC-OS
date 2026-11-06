import { defineConfig, devices } from "@playwright/test";

/**
 * STONE-GATE / DEF-003 browser acceptance against a DEPLOYED STAGING build
 * (approval item A2). Kept separate from playwright.config.ts, which stays
 * hard-wired to localhost by design.
 *
 * Fail-closed origin guard: both URLs must be given explicitly, must be
 * https, and must not look like production. A local dry run is allowed only
 * with STAGING_DRY_RUN_LOCAL=1 and loopback URLs. Nothing here starts a
 * server, signs up a user or touches a database: the synthetic owner is
 * provisioned beforehand (scripts/qa/provision_synthetic_owner.py) and its
 * credentials arrive through the environment, never through the repository.
 *
 *   STAGING_WEB_URL, STAGING_API_URL, STAGING_OWNER_EMAIL, STAGING_OWNER_PASSWORD
 *   optional: STAGING_OTHER_OWNER_EMAIL / STAGING_OTHER_OWNER_PASSWORD (tenant B)
 *   pnpm exec playwright test -c playwright.staging.config.ts
 */

const PRODUCTION_HINTS = [/geocore\.one$/i, /production/i, /^app\./i, /^api\./i];
const LOOPBACK = new Set(["localhost", "127.0.0.1"]);

export function checkedOrigin(name: string): string {
  const raw = process.env[name];
  if (!raw) throw new Error(`${name} is required`);
  const url = new URL(raw);
  const dryRun = process.env.STAGING_DRY_RUN_LOCAL === "1";
  if (LOOPBACK.has(url.hostname)) {
    if (!dryRun) throw new Error(`${name} is loopback; set STAGING_DRY_RUN_LOCAL=1 for a local dry run`);
    return url.origin;
  }
  if (dryRun) throw new Error("STAGING_DRY_RUN_LOCAL=1 only allows loopback URLs");
  if (url.protocol !== "https:") throw new Error(`${name} must be https`);
  if (PRODUCTION_HINTS.some((hint) => hint.test(url.hostname))) {
    throw new Error(`${name} (${url.hostname}) looks like production; refusing`);
  }
  if (!/staging/i.test(url.hostname)) throw new Error(`${name} (${url.hostname}) is not a staging host`);
  return url.origin;
}

export const STAGING_WEB_URL = checkedOrigin("STAGING_WEB_URL");
export const STAGING_API_URL = checkedOrigin("STAGING_API_URL");

export default defineConfig({
  testDir: "./e2e-staging",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "staging-acceptance-results/results.json" }]],
  outputDir: "staging-acceptance-results/artifacts",
  use: {
    baseURL: STAGING_WEB_URL,
    trace: "on",
    screenshot: "on",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
