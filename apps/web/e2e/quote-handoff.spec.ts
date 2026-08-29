import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 020 — first true browser E2E test. Setup (tenant/customer/quote)
 * goes through the real API directly (same payload shapes as
 * tests/test_quote_handoff.py's `_create_linked_quote`), but the critical
 * business transition — Approve, then Hand off to Project — runs through
 * the real Chromium browser against the real Next.js app and real FastAPI
 * server (see playwright.config.ts's webServer). Nothing here mocks
 * fetch, the router, or the API client.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 020 Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint020-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint020-password-${RUN_ID}`;
const CUSTOMER_NAME = `Pytest E2E Sprint 020 Customer ${RUN_ID}`;

test("customer_quote_approval_handoff_persists_project", async ({ page }) => {
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
  const { access_token: token } = await signup.json();
  const authHeaders = { Authorization: `Bearer ${token}` };

  const customerRes = await api.post("/api/v1/customers", {
    headers: authHeaders,
    data: { name: CUSTOMER_NAME },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customer = await customerRes.json();

  const quoteCreateRes = await api.post("/api/v1/quote", {
    headers: authHeaders,
    data: {
      customer: CUSTOMER_NAME,
      customer_id: customer.id,
      material: "Calacatta Gold",
      thickness: "20mm",
      kitchen_length: 3,
      postcode: "E2E-020",
    },
  });
  expect(quoteCreateRes.ok()).toBeTruthy();
  const quoteId = (await quoteCreateRes.json()).id as string;

  // ---- Lock the source Quote's authoritative state before entering the browser ----
  const lockedQuoteRes = await api.get(`/api/v1/quotes/${quoteId}`, {
    headers: authHeaders,
  });
  expect(lockedQuoteRes.ok()).toBeTruthy();
  const lockedQuote = await lockedQuoteRes.json();
  expect(lockedQuote.status).toBe("draft");

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

  // ---- Open the real Quote detail page ----
  await page.goto(`/quotes/${quoteId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  const approveButton = page.getByRole("button", { name: "Approve" });
  await expect(approveButton).toBeVisible();

  // ---- Approve through the UI (not a direct API call) ----
  await approveButton.click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  await expect(approveButton).not.toBeVisible();
  const handoffButton = page.getByRole("button", { name: "Hand off to Project" });
  await expect(handoffButton).toBeVisible();

  // ---- Hand off through the UI — the server-returned Project id is authoritative ----
  await handoffButton.click();
  await page.waitForURL(/\/projects\/.+/);
  const projectId = page.url().split("/projects/")[1];
  expect(projectId).toBeTruthy();

  // ---- Verify the real Project page ----
  await expect(page.getByText("Booked", { exact: true })).toBeVisible();

  // ---- Verify persistence: reload proves it was saved, not just client state ----
  await page.reload();
  await expect(page.getByText("Booked", { exact: true })).toBeVisible();

  // ---- Verify Quote linkage through the live API (not rendered in the UI) ----
  const projectRes = await api.get(`/api/v1/projects/${projectId}`, {
    headers: authHeaders,
  });
  expect(projectRes.ok()).toBeTruthy();
  const project = await projectRes.json();
  expect(project.id).toBe(projectId);
  expect(project.quote_id).toBe(quoteId);
  expect(project.customer_id).toBe(customer.id);
  expect(project.status).toBe("booked");

  // ---- Verify exactly one Project exists for this Quote ----
  // GET /api/v1/projects exposes quote_id per-row (same ProjectOut model as
  // GET /api/v1/projects/{id}), so the existing list endpoint is enough —
  // no production field was added solely for this test.
  const projectsListRes = await api.get("/api/v1/projects?limit=50", {
    headers: authHeaders,
  });
  expect(projectsListRes.ok()).toBeTruthy();
  const projects = await projectsListRes.json();
  const matchingProjects = projects.filter((p: { quote_id: string | null }) => p.quote_id === quoteId);
  expect(matchingProjects).toHaveLength(1);

  await api.dispose();
});
