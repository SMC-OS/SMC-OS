import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 028 UAT acceptance matrix AT-04 — logout was never exercised by
 * any existing spec (every prior spec signs up/logs in but none signs
 * out). Setup (tenant/Owner) goes through the real API directly; signing
 * in and out runs through the real Chromium browser against the real
 * Next.js app and real FastAPI server (see playwright.config.ts's
 * webServer) — nothing here mocks fetch, the router, or the API client.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 028 Logout Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint028-logout-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint028-logout-password-${RUN_ID}`;
const OWNER_NAME = "Pytest E2E Logout Owner";

test("logging_out_terminates_the_session_and_protected_routes_redirect_to_login", async ({
  page,
}) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Setup through the real API (not TestClient, not mocked) ----
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: COMPANY_NAME,
      name: OWNER_NAME,
      email: OWNER_EMAIL,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();

  // ---- Authenticate through the real login UI ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // ---- UAT-001 regression: the header shows the real signed-in identity ----
  const profileButton = page.getByRole("button", { name: new RegExp(OWNER_NAME, "i") });
  await expect(profileButton).toBeVisible();

  // ---- Sign out through the real profile menu ----
  await profileButton.click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // ---- Session is actually terminated: a protected route redirects again ----
  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/login$/);

  await api.dispose();
});
