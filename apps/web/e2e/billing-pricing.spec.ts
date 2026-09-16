import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 3 — true browser
 * E2E for the locked 4-tier pricing catalogue and the automatic 14-day
 * trial. Setup (tenant/Owner) goes through the real API directly; the
 * pricing page, trial state, and checkout's honest "not configured yet"
 * fallback all run through the real Chromium browser against the real
 * Next.js app and real FastAPI server. No real Stripe checkout is
 * exercised here — Stripe is genuinely unconfigured in this environment
 * (no test-mode keys are available), so this spec proves the product is
 * honest about that rather than faking success (see
 * app/billing/service.py's "ships dark until configured" contract).
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 039 Billing Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint039-billing-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint039-billing-password-${RUN_ID}`;
const OWNER_NAME = "Pytest E2E Billing Owner";

test("pricing_page_shows_the_locked_four_tier_catalogue_and_new_owner_is_on_a_trial", async ({
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
  await expect(page).toHaveURL(/\/(customers|onboarding)/);

  // ---- The real pricing page, real API-served catalogue ----
  await page.goto("/pricing");
  await page.waitForLoadState("networkidle");

  // By heading: each plan name also appears inside its own "Upgrade to
  // ..." / "Choose ..." button, so a plain text match is ambiguous.
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

  // ---- The new owner is automatically on a trial of the Pro plan ----
  // exact: true — the countdown banner's own text ("...left in your
  // trial") case-insensitively contains "Your trial" too, which would
  // otherwise make this a strict-mode violation against the badge.
  await expect(page.getByText(/days left in your trial/i)).toBeVisible();
  await expect(page.getByText("Your trial", { exact: true })).toBeVisible();

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
  await expect(page).toHaveURL(/\/(customers|onboarding)/);

  await page.goto("/pricing");
  await page.waitForLoadState("networkidle");

  // The trialing Owner is offered an upgrade (not a fresh "Choose" CTA)
  // on the plan they're already trialing.
  await page.getByRole("button", { name: /upgrade to geocore business/i }).click();

  // Stripe genuinely isn't configured in this environment — the product
  // must say so honestly, never fake a successful checkout redirect.
  await expect(
    page.getByText(/billing isn't fully configured yet/i)
  ).toBeVisible();

  await api.dispose();
});
