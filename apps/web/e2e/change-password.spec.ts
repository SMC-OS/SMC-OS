import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * Settings > Security "Change password", end to end through the real
 * browser, Next.js app and FastAPI server: a wrong current password is
 * refused, a correct change keeps this session signed in, signs the
 * other session out, and the new password (not the old one) signs in.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const OWNER_EMAIL = `pytest-e2e-change-password-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `Pytest-E2e-Change-Password-${RUN_ID}!`;
const NEW_PASSWORD = `Pytest-E2e-Changed-Password-${RUN_ID}!`;

async function signIn(page: import("@playwright/test").Page, password: string) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("change_password_from_settings_keeps_this_session_and_revokes_others", async ({
  page,
  browser,
}) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Change Password Co ${RUN_ID}`,
      name: "Pytest E2E Change Password Owner",
      email: OWNER_EMAIL,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(OWNER_EMAIL);
  grantBillingAccess(OWNER_EMAIL);

  // A second device, signed in before the change.
  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  await signIn(otherPage, OWNER_PASSWORD);
  await expect(otherPage).toHaveURL(/\/(customers|onboarding)/);

  await signIn(page, OWNER_PASSWORD);
  await expect(page).toHaveURL(/\/(customers|onboarding)/);
  await page.goto("/settings?section=security");
  await page.waitForLoadState("networkidle");

  const form = page.getByRole("form", { name: "Change password" });
  await expect(form).toBeVisible();

  // Wrong current password: refused, still signed in.
  await form.getByLabel("Current password").fill("Not-The-Password-1!");
  await form.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await form.getByLabel("Confirm new password").fill(NEW_PASSWORD);
  await form.getByRole("button", { name: "Change password" }).click();
  await expect(form.getByText("Your current password is incorrect.")).toBeVisible();
  await expect(page).toHaveURL(/\/settings/);

  // Correct change.
  await form.getByLabel("Current password").fill(OWNER_PASSWORD);
  await form.getByRole("button", { name: "Change password" }).click();
  await expect(form.getByRole("status")).toContainText("Your password has been changed");

  // This session stays signed in on a fresh token.
  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/customers/);

  // The other device is signed out server-side.
  await otherPage.goto("/customers");
  await otherPage.waitForLoadState("networkidle");
  await expect(otherPage).toHaveURL(/\/login$/);

  // Old password no longer works; the new one does.
  const fresh = await browser.newContext();
  const freshPage = await fresh.newPage();
  await signIn(freshPage, OWNER_PASSWORD);
  await expect(freshPage.getByText("Incorrect email or password.")).toBeVisible();
  await freshPage.getByLabel("Password").fill(NEW_PASSWORD);
  await freshPage.getByRole("button", { name: "Sign in" }).click();
  await expect(freshPage).toHaveURL(/\/(customers|onboarding)/);

  await fresh.close();
  await otherContext.close();
  await api.dispose();
});
