import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";
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
const OWNER_PASSWORD = `Pytest-E2e-Sprint028-Logout-Password-${RUN_ID}!`;
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
  markVerified(OWNER_EMAIL);
  grantBillingAccess(OWNER_EMAIL);
  // ---- Authenticate through the real login UI ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // SEC001: a real browser receives host-only HttpOnly cookies, never a
  // JavaScript-readable bearer credential. Reload restores via /auth/me.
  const cookies = await page.context().cookies(BACKEND_URL);
  const session = cookies.find((cookie) => cookie.name === "geocore_session");
  expect(session).toBeDefined();
  expect(session!.httpOnly).toBe(true);
  expect(session!.sameSite).toBe("Lax");
  expect(session!.domain).toBe("localhost");
  const browserTokens = await page.evaluate(() => ({
    current: localStorage.getItem("geocore-token"),
    legacy: localStorage.getItem("simo-os-token"),
    session: sessionStorage.getItem("geocore-token"),
    cookies: document.cookie,
  }));
  expect(browserTokens.current).toBeNull();
  expect(browserTokens.legacy).toBeNull();
  expect(browserTokens.session).toBeNull();
  expect(browserTokens.cookies).not.toContain("geocore_session=");
  await page.reload();
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

  // The old credential is rejected server-side, even outside the browser.
  const replay = await api.get("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${session!.value}` },
  });
  expect(replay.status()).toBe(401);
  expect((await page.context().cookies(BACKEND_URL)).some((cookie) => cookie.name === "geocore_session")).toBe(false);
  await page.goBack();
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/login$/);
  await page.goForward();
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/login$/);
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
  await api.dispose();
});
