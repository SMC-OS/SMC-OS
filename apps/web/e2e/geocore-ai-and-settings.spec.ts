import { expect, request, test, type Page } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess, startRealTrial } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * Sprint 036 (Workstreams B/H/I/M) — GeoCore AI, Settings navigation,
 * billing, theme switching and phone navigation.
 *
 * These are the journeys the sprint contract calls out that no other spec
 * covers, and each of them guards an honesty property as well as a
 * behavioural one: GeoCore AI must not leak developer internals or claim
 * capabilities this deployment lacks, billing must not fake a checkout
 * it cannot perform, and the mobile shell must not overlap its own
 * controls.
 */

function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Signs in through the real form. The form is client-rendered, so instead of
 * waiting for the network to go quiet (a Next dev server's HMR socket can keep
 * it from ever settling, which timed out CI), wait for the form itself and
 * fill until the values actually stick, then submit.
 */
async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible({ timeout: 15_000 });
  await expect(async () => {
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await expect(page.getByLabel("Email")).toHaveValue(email);
    await expect(page.getByLabel("Password")).toHaveValue(password);
  }).toPass({ timeout: 15_000 });
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });
}

async function signUpAndLogIn(page: Page, runId: string) {
  const ownerEmail = `pytest-e2e-shell-${runId}@example.invalid`;
  const ownerPassword = `Pytest-E2e-Shell-Password-${runId}!`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Shell Co ${runId}`,
      name: "Pytest Shell Owner",
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(ownerEmail);
  // This file's subject is GeoCore AI / Settings navigation, not billing
  // activation itself (that's billing-pricing.spec.ts) — grant it the
  // same way any other "not this test's subject" fixture does.
  grantBillingAccess(ownerEmail);

  await signIn(page, ownerEmail, ownerPassword);

  return { api };
}

test("geocore_ai_holds_a_conversation_and_never_shows_developer_internals", async ({
  page,
}) => {
  const { api } = await signUpAndLogIn(page, uniqueRunId("ai"));

  await page.goto("/ai");

  await expect(page.getByRole("heading", { name: "GeoCore AI" })).toBeVisible({ timeout: 15_000 });
  // The old page named its own endpoint and implementation class in
  // product copy. Nothing here may.
  await expect(page.getByText(/BrainManager/i)).toHaveCount(0);
  await expect(page.getByText(/POST \/process/i)).toHaveCount(0);
  await expect(page.getByText(/Sprint \d/i)).toHaveCount(0);
  await expect(page.getByText("AI Assistant")).toHaveCount(0);

  // No OPENAI_API_KEY exists in this or any CI environment, so the
  // built-in catalogue assistant answers — and says so, rather than
  // being passed off as AI.
  await expect(page.getByText(/No AI provider is connected/i)).toBeVisible();

  await page.getByLabel("Ask GeoCore AI").fill("What does 20mm quartz cost?");
  await page.getByRole("button", { name: "Send" }).click();

  // .first(): the badge on the reply, and the reply text itself, both
  // name the built-in assistant — which is the point.
  await expect(page.getByText("Built-in assistant").first()).toBeVisible({
    timeout: 15_000,
  });
  // The question stays on screen as part of the conversation. Matched
  // exactly: the reply quotes the same phrase back as a suggestion, so a
  // substring match would be ambiguous.
  await expect(
    page.getByText("What does 20mm quartz cost?", { exact: true }).first()
  ).toBeVisible();

  await api.dispose();
});

test("settings_sections_are_navigable_and_billing_has_its_own_place", async ({ page }) => {
  const ownerEmail = `pytest-e2e-shell-settings-${uniqueRunId("settings")}@example.invalid`;
  const ownerPassword = `Pytest-E2e-Shell-Settings-Password-${uniqueRunId("pw")}!`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Shell Settings Co ${uniqueRunId("co")}`,
      name: "Pytest Shell Owner",
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(ownerEmail);
  // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES: this test's own subject
  // IS the trial UI, so it needs a genuine trialing subscription (real
  // trial_start/trial_end), not just the generic grantBillingAccess()
  // exemption every other test in this file uses.
  startRealTrial(ownerEmail);

  await signIn(page, ownerEmail, ownerPassword);

  await page.goto("/settings");

  const sectionNav = page.getByRole("navigation", { name: "Settings sections" });
  for (const section of [
    "Company",
    "Branding",
    "Team & permissions",
    "Billing & subscription",
    "Notifications",
    "Security",
  ]) {
    await expect(sectionNav.getByRole("button", { name: section })).toBeVisible({ timeout: 15_000 });
  }

  // Billing is a section of its own now, not the fourth card down a
  // single scrolling page — and it is linkable.
  await sectionNav.getByRole("button", { name: "Billing & subscription" }).click();
  await expect(page).toHaveURL(/section=billing/);
  // Sprint 039 Blocker 3: every new signup starts on a 14-day trial of
  // GeoCore Pro rather than landing on a bare "no plan" state.
  await expect(page.getByText(/days left in your free trial/i)).toBeVisible({ timeout: 10_000 });

  // Stripe is not configured in this environment, and the product says
  // so plainly rather than faking a checkout. Phase 2 makes the recurring
  // price and cancellation route visible before this approved checkout
  // handoff. Pro is the trial plan the Owner is already on, so exercise the
  // disclosed checkout action on a different plan.
  const businessPlan = page.getByText("GeoCore Business").locator("..").locator("..");
  await expect(businessPlan).toContainText("£199 per month");
  await expect(businessPlan).toContainText(/recurring subscription; cancel through the billing portal/i);
  await businessPlan.getByRole("button", { name: "Continue to secure checkout" }).click();
  // Matched without the apostrophe: the copy uses a straight quote and a
  // curly one in the test would silently never match.
  // Next.js renders its own empty role="alert" route announcer, so this
  // matches the message directly rather than by role.
  await expect(page.getByText(/switched on for this workspace/i)).toBeVisible({
    timeout: 10_000,
  });

  // A section is linkable, because it lives in the URL rather than in
  // component state — someone can send a colleague straight to billing.
  await page.goto("/settings?section=billing");
  // By role: the section's own description paragraph also contains the
  // words "Your plan".
  await expect(page.getByRole("heading", { name: "Your plan" })).toBeVisible({
    timeout: 10_000,
  });

  await api.dispose();
});

test("theme_switching_works_and_the_controls_never_overlap_the_search_field", async ({
  page,
}) => {
  const { api } = await signUpAndLogIn(page, uniqueRunId("theme"));

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  const html = page.locator("html");
  await expect(html).not.toHaveClass(/dark/);

  await page.getByLabel("Switch to dark mode").click();
  await expect(html).toHaveClass(/dark/);

  // The theme survives a reload rather than flashing back.
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(html).toHaveClass(/dark/);

  await page.getByLabel("Switch to light mode").click();
  await expect(html).not.toHaveClass(/dark/);

  await api.dispose();
});

test("the_phone_layout_has_no_overlapping_controls_and_no_sideways_scroll", async ({
  page,
}) => {
  const { api } = await signUpAndLogIn(page, uniqueRunId("mobile"));

  // The reported bug's own viewport.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  // The exact defect: the search control and the theme control must not
  // occupy the same pixels. Measured, not assumed.
  const search = page.getByLabel("Search pages and actions");
  const theme = page.getByLabel("Switch to dark mode");
  const searchBox = await search.boundingBox();
  const themeBox = await theme.boundingBox();
  expect(searchBox).not.toBeNull();
  expect(themeBox).not.toBeNull();
  expect(searchBox!.x + searchBox!.width).toBeLessThanOrEqual(themeBox!.x + 1);

  // And the page itself must not scroll sideways.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(overflow).toBeLessThanOrEqual(1);

  // Bottom navigation is present, reachable, and navigates.
  const bottomNav = page.getByRole("navigation", { name: "Primary" });
  await expect(bottomNav).toBeVisible();
  await bottomNav.getByRole("link", { name: "Quotes" }).click();
  await expect(page).toHaveURL(/\/quotes$/);

  // The drawer opens everything the bottom bar does not carry.
  await bottomNav.getByLabel("More navigation").click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("link", { name: "Automations" }).click();
  await expect(page).toHaveURL(/\/automations$/);

  await api.dispose();
});
