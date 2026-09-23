import { expect, request, test, type Page } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { removeSubscription } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * Phase B — true browser E2E for the 14-day no-card trial and the locked
 * 4-tier pricing catalogue. (This spec previously proved the superseded
 * card-required contract; see git history.) Setup goes through the real
 * API; the pricing page, trial states, access gate and checkout's honest
 * "not configured yet" fallback all run in real Chromium against the real
 * Next.js app and FastAPI server.
 *
 * Stripe is unconfigured in this sandbox, so no real Checkout completes
 * here; a real Stripe TEST Checkout must be exercised once on staging.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 039 Billing Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint039-billing-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `Pytest-E2e-Sprint039-Billing-Password-${RUN_ID}!`;
const OWNER_NAME = "Pytest E2E Billing Owner";

async function signUpAndSignIn(page: Page, { email, company, plan }: { email: string; company: string; plan?: string }) {
  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: company,
      name: OWNER_NAME,
      email,
      password: OWNER_PASSWORD,
      ...(plan ? { plan, billing_period: "monthly" } : {}),
    },
  });
  expect(signup.ok()).toBeTruthy();
  await api.dispose();
  markVerified(email);
  return async () => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(OWNER_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
  };
}

test("a_new_signup_gets_a_no_card_trial_and_reaches_the_workspace", async ({ page }) => {
  const signIn = await signUpAndSignIn(page, { email: OWNER_EMAIL, company: COMPANY_NAME, plan: "team" });
  await signIn();

  // No card, no Checkout: straight into the workspace.
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });
  await expect(page.getByText("14 days left")).toBeVisible();

  await page.goto("/pricing");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("14 days left in your free trial")).toBeVisible();
  await expect(page.getByText(/card is required/i)).toHaveCount(0);

  // The locked catalogue; the plan chosen at signup is the trial plan.
  for (const name of ["GeoCore Starter", "GeoCore Team", "GeoCore Pro", "GeoCore Business", "Enterprise"]) {
    await expect(page.getByRole("heading", { name })).toBeVisible();
  }
  await expect(page.getByText("Your trial", { exact: true })).toBeVisible();
  // Monthly was chosen at signup, so monthly prices show.
  await expect(page.getByText("£59").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe to GeoCore Team" })).toBeVisible();
});

test("a_workspace_with_no_subscription_lands_on_pricing_and_can_start_the_trial", async ({ page }) => {
  const email = `pytest-e2e-phaseb-bare-${RUN_ID}@example.invalid`;
  const signIn = await signUpAndSignIn(page, { email, company: `Pytest E2E Phase B Bare Co ${RUN_ID}` });
  removeSubscription(email);
  await signIn();

  await expect(page).toHaveURL(/\/pricing$/, { timeout: 15_000 });
  // The gate is not just "no link": direct navigation is sent back.
  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/pricing$/);

  await page.getByRole("button", { name: "Start free trial" }).click();
  await expect(page).toHaveURL(/\/(onboarding|customers|)$/, { timeout: 15_000 });
  await page.goto("/customers");
  await expect(page).toHaveURL(/\/customers$/);
});

test("checkout_is_honest_about_stripe_not_being_configured_yet", async ({ page }) => {
  const email = `pytest-e2e-phaseb-checkout-${RUN_ID}@example.invalid`;
  const signIn = await signUpAndSignIn(page, { email, company: `Pytest E2E Phase B Checkout Co ${RUN_ID}` });
  await signIn();
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });

  await page.goto("/pricing");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /subscribe to geocore business/i }).click();

  // Stripe genuinely isn't configured here — the product says so and
  // never fakes a successful checkout.
  await expect(page.getByText(/billing isn't fully configured yet/i)).toBeVisible();
  await expect(page).toHaveURL(/\/pricing$/);
});
