import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES. True browser E2E for the
 * locked 4-tier pricing catalogue and the card-required-trial access
 * boundary. Setup (tenant/Owner) goes through the real API directly;
 * the pricing page, the access gate, and checkout's honest "not
 * configured yet" fallback all run through the real Chromium browser
 * against the real Next.js app and real FastAPI server.
 *
 * No real Stripe Checkout is exercised here — Stripe is genuinely
 * unconfigured in this sandbox (no TEST-mode keys available), so this
 * spec proves the product is honest about that rather than faking
 * success (see app/billing/service.py's "ships dark until configured"
 * contract) and proves the access boundary itself holds for a real
 * browser session. A real Stripe TEST Checkout completing end-to-end
 * (card collection, webhook-driven activation) needs to be exercised
 * once on staging, with real Stripe TEST keys configured, by the owner —
 * see the release report's own disclosed limitation.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 039 Billing Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint039-billing-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `Pytest-E2e-Sprint039-Billing-Password-${RUN_ID}!`;
const OWNER_NAME = "Pytest E2E Billing Owner";

test("a_verified_new_owner_with_no_subscription_lands_on_pricing_and_cannot_bypass_it", async ({
  page,
}) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: COMPANY_NAME,
      name: OWNER_NAME,
      email: OWNER_EMAIL,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(OWNER_EMAIL);

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES: a verified account with
  // no Subscription at all lands on /pricing, not the workspace.
  await expect(page).toHaveURL(/\/pricing$/, { timeout: 15_000 });

  // ---- Direct navigation to a protected route redirects back here too
  // (the gate is not just "don't show a link to it") ----
  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/pricing$/);

  // ---- The real pricing page, real API-served catalogue ----
  // By heading: each plan name also appears inside its own "Choose ..."
  // button, so a plain text match is ambiguous.
  await expect(page.getByRole("heading", { name: "GeoCore Starter" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "GeoCore Team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "GeoCore Pro" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "GeoCore Business" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Enterprise" })).toBeVisible();

  // Annual is the default toggle — locked prices, not the old £79/£149.
  await expect(page.getByText("£290").first()).toBeVisible();
  await expect(page.getByText("£590").first()).toBeVisible();
  await expect(page.getByText("£990").first()).toBeVisible();
  await expect(page.getByText("£1,990").first()).toBeVisible();

  await page.getByRole("button", { name: "Monthly" }).click();
  await expect(page.getByText("£29").first()).toBeVisible();
  await expect(page.getByText("£59").first()).toBeVisible();
  await expect(page.getByText("£99").first()).toBeVisible();
  await expect(page.getByText("£199").first()).toBeVisible();

  // ---- No automatic trial — the owner's decision superseded the old
  // no-card trial. No plan is pre-selected, nothing claims "Your trial". ----
  await expect(page.getByText(/days left in your trial/i)).toHaveCount(0);
  await expect(page.getByText("Your trial", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /choose geocore pro/i })).toBeVisible();

  await api.dispose();
});

test("checkout_is_honest_about_stripe_not_being_configured_yet", async ({ page }) => {
  const email = `pytest-e2e-sprint039-billing-checkout-${RUN_ID}@example.invalid`;
  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 039 Checkout Co ${RUN_ID}`,
      name: OWNER_NAME,
      email,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(email);

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/pricing$/, { timeout: 15_000 });

  // No subscription exists yet, so every plan offers a fresh "Choose",
  // not an "Upgrade" (that only applies once already on a plan).
  await page.getByRole("button", { name: /choose geocore business/i }).click();

  // Stripe genuinely isn't configured in this environment — the product
  // must say so honestly, never fake a successful checkout redirect, and
  // the owner stays exactly where they were (still gated, not
  // accidentally let through).
  await expect(
    page.getByText(/billing isn't fully configured yet/i)
  ).toBeVisible();
  await expect(page).toHaveURL(/\/pricing$/);

  await api.dispose();
});
