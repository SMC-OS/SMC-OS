import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.11/§8) — ADR-029's tenant
 * isolation is proven thoroughly at the API layer (every module's own
 * test file, plus scripts/staging/smoke.py's tenant_isolation gate), but
 * no test before this one proved it through the *browser*: that
 * Tenant B's authenticated session, navigating the real UI, sees a clean
 * "not found" state rather than a raw error or a leak of Tenant A's data.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const TENANT_A_EMAIL = `pytest-e2e-sprint027-xtenant-a-${RUN_ID}@example.invalid`;
const TENANT_A_PASSWORD = `pytest-e2e-sprint027-xtenant-a-password-${RUN_ID}`;
const TENANT_A_COMPANY = `Pytest E2E Sprint 027 Tenant A ${RUN_ID}`;

const TENANT_B_EMAIL = `pytest-e2e-sprint027-xtenant-b-${RUN_ID}@example.invalid`;
const TENANT_B_PASSWORD = `pytest-e2e-sprint027-xtenant-b-password-${RUN_ID}`;
const TENANT_B_COMPANY = `Pytest E2E Sprint 027 Tenant B ${RUN_ID}`;

test("tenant_b_sees_a_clean_not_found_state_for_tenant_a_resources_through_the_ui", async ({
  page,
}) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Tenant A: create a customer, project, quote through the real API ----
  const signupA = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: TENANT_A_COMPANY,
      name: "Pytest Tenant A Owner",
      email: TENANT_A_EMAIL,
      password: TENANT_A_PASSWORD,
    },
  });
  expect(signupA.ok()).toBeTruthy();
  markVerified(TENANT_A_EMAIL);
  const { access_token: tenantAToken } = await signupA.json();
  const tenantAHeaders = { Authorization: `Bearer ${tenantAToken}` };

  const customerRes = await api.post("/api/v1/customers", {
    headers: tenantAHeaders,
    data: { name: `Pytest E2E Sprint 027 Tenant A Customer ${RUN_ID}` },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customerId = (await customerRes.json()).id as string;

  const projectRes = await api.post("/api/v1/projects", {
    headers: tenantAHeaders,
    data: { name: `Pytest E2E Sprint 027 Tenant A Project ${RUN_ID}`, customer_id: customerId },
  });
  expect(projectRes.ok()).toBeTruthy();
  const projectId = (await projectRes.json()).id as string;

  const quoteRes = await api.post("/api/v1/quote", {
    headers: tenantAHeaders,
    data: {
      customer: `Pytest E2E Sprint 027 Tenant A Customer ${RUN_ID}`,
      customer_id: customerId,
      material: "Calacatta Gold",
      thickness: "20mm",
      kitchen_length: 3.2,
    },
  });
  expect(quoteRes.ok()).toBeTruthy();
  const quoteId = (await quoteRes.json()).id as string;

  // ---- Tenant B: a second, fully separate tenant ----
  const signupB = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: TENANT_B_COMPANY,
      name: "Pytest Tenant B Owner",
      email: TENANT_B_EMAIL,
      password: TENANT_B_PASSWORD,
    },
  });
  expect(signupB.ok()).toBeTruthy();
  markVerified(TENANT_B_EMAIL);

  // ---- Authenticate as Tenant B through the real login UI ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(TENANT_B_EMAIL);
  await page.getByLabel("Password").fill(TENANT_B_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // ---- Tenant B navigates directly to each of Tenant A's resource URLs ----
  await page.goto(`/customers/${customerId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Customer not found.")).toBeVisible();
  await expect(page.getByText(`Pytest E2E Sprint 027 Tenant A Customer ${RUN_ID}`)).not.toBeVisible();

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Project not found.")).toBeVisible();
  await expect(page.getByText(`Pytest E2E Sprint 027 Tenant A Project ${RUN_ID}`)).not.toBeVisible();

  await page.goto(`/quotes/${quoteId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Quote not found.")).toBeVisible();

  await api.dispose();
});
