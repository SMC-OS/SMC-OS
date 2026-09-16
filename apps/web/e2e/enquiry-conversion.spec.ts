import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * Sprint 021 — true browser E2E for enquiry-to-customer conversion.
 * Structural twin of e2e/quote-handoff.spec.ts (Sprint 020). Setup (tenant +
 * unlinked enquiry Project) goes through the real API directly (same
 * payload shapes as tests/test_enquiry_conversion.py), but the critical
 * business transition — clicking "Convert to Customer" and submitting the
 * form — runs through the real Chromium browser against the real Next.js
 * app and real FastAPI server (see playwright.config.ts's webServer).
 * Nothing here mocks fetch, the router, or the API client;
 * page.waitForResponse below only observes the real network response, it
 * never intercepts or fulfills it.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 021 Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint021-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint021-password-${RUN_ID}`;
const PROJECT_NAME = `Pytest E2E Sprint 021 Project ${RUN_ID}`;
const CUSTOMER_NAME = `Pytest E2E Sprint 021 Customer ${RUN_ID}`;
const CUSTOMER_EMAIL = `sprint021-e2e-${RUN_ID}@example.invalid`;
const CUSTOMER_PHONE = "07000 000000";

test("unlinked_enquiry_can_be_converted_to_customer_and_persists", async ({ page }) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Setup through the real API (not TestClient, not mocked) ----
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: COMPANY_NAME,
      name: "Pytest E2E Owner",
      email: OWNER_EMAIL,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(OWNER_EMAIL);
  const { access_token: token } = await signup.json();
  const authHeaders = { Authorization: `Bearer ${token}` };

  const projectRes = await api.post("/api/v1/projects", {
    headers: authHeaders,
    data: { name: PROJECT_NAME },
  });
  expect(projectRes.ok()).toBeTruthy();
  const projectId = (await projectRes.json()).id as string;

  // ---- Lock the source Project's authoritative state before entering the browser ----
  const lockedProjectRes = await api.get(`/api/v1/projects/${projectId}`, {
    headers: authHeaders,
  });
  expect(lockedProjectRes.ok()).toBeTruthy();
  const lockedProject = await lockedProjectRes.json();
  expect(lockedProject.status).toBe("enquiry");
  expect(lockedProject.customer_id).toBeNull();

  // ---- Authenticate through the real login UI ----
  // networkidle after each full navigation: Next dev/Turbopack compiles a
  // route on first visit, and a Playwright click can otherwise land before
  // React attaches the form's onSubmit handler, causing a native (non-JS)
  // form submission instead of the real login request.
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // ---- Open the real Project detail page ----
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Enquiry", { exact: true })).toBeVisible();
  await expect(page.getByText("—", { exact: true }).first()).toBeVisible();
  const convertButton = page.getByRole("button", { name: "Convert to Customer" });
  await expect(convertButton).toBeVisible();

  // ---- Convert through the UI (not a direct API call) ----
  await convertButton.click();
  await page.getByLabel("Full name").fill(CUSTOMER_NAME);
  await page.getByLabel("Email").fill(CUSTOMER_EMAIL);
  await page.getByLabel("Phone").fill(CUSTOMER_PHONE);

  const conversionResponsePromise = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/projects/${projectId}/convert-to-customer`) &&
      res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Save customer" }).click();
  const conversionResponse = await conversionResponsePromise;
  expect(conversionResponse.status()).toBe(200);
  const returnedCustomer = await conversionResponse.json();
  expect(returnedCustomer.id).toBeTruthy();

  // ---- Verify the real Project page reflects the returned Customer ----
  await expect(page.getByRole("link", { name: CUSTOMER_NAME })).toBeVisible();
  await expect(convertButton).not.toBeVisible();

  // ---- Verify persistence: reload proves it was saved, not just client state ----
  await page.reload();
  await expect(page.getByRole("link", { name: CUSTOMER_NAME })).toBeVisible();
  await expect(page.getByRole("button", { name: "Convert to Customer" })).not.toBeVisible();

  // ---- Verify Project linkage through the live API (server-side truth) ----
  const persistedProjectRes = await api.get(`/api/v1/projects/${projectId}`, {
    headers: authHeaders,
  });
  expect(persistedProjectRes.ok()).toBeTruthy();
  const persistedProject = await persistedProjectRes.json();
  expect(persistedProject.id).toBe(projectId);
  expect(persistedProject.customer_id).toBe(returnedCustomer.id);
  expect(persistedProject.status).toBe("enquiry");

  // ---- Verify the created Customer through the live API ----
  const persistedCustomerRes = await api.get(`/api/v1/customers/${returnedCustomer.id}`, {
    headers: authHeaders,
  });
  expect(persistedCustomerRes.ok()).toBeTruthy();
  const persistedCustomer = await persistedCustomerRes.json();
  expect(persistedCustomer.name).toBe(CUSTOMER_NAME);
  expect(persistedCustomer.email).toBe(CUSTOMER_EMAIL);
  expect(persistedCustomer.phone).toBe(CUSTOMER_PHONE);

  // ---- Verify exactly one enquiry_converted activity exists for this
  // transition (tenant-scoped: GET /activity is always the caller's own
  // tenant — see app/activity/router.py) ----
  const activityRes = await api.get("/api/v1/activity?limit=50&type=enquiry_converted", {
    headers: authHeaders,
  });
  expect(activityRes.ok()).toBeTruthy();
  const activity = await activityRes.json();
  const matchingActivity = activity.filter(
    (event: { description: string | null }) =>
      event.description === `Project ${projectId} converted to customer ${returnedCustomer.id}`
  );
  expect(matchingActivity).toHaveLength(1);

  await api.dispose();
});
