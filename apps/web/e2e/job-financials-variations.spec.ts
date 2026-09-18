import { expect, request, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * GeoCore Premium OS Plan 04 (Sprint 043) — end-to-end coverage for the
 * project commercial-control layer, through the real browser against the
 * real Next.js app and real FastAPI server. Journeys A-F from the sprint
 * contract:
 *   A. Construction Project Financials — budgeted/committed/actual costs
 *      roll up correctly on a General Building project.
 *   B. Variation — create, send, approve; Current Contract increases
 *      exactly once.
 *   C. Idempotency — a repeat approval never double-counts.
 *   D. Margin — forecast profit/margin appear and recalculate as costs
 *      are added.
 *   E. Tenant Isolation — a second tenant gets a clean 404, no leak.
 *   F. Stone Regression — the stone catalogue quote -> project ->
 *      Financials path still works, unaffected by this sprint.
 */

function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: Page, runId: string) {
  const ownerEmail = `pytest-e2e-043-${runId}@example.invalid`;
  const ownerPassword = `Pytest-E2e-043-Password-${runId}!`;
  const customerName = `Pytest E2E 043 Customer ${runId}`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 043 Co ${runId}`,
      name: "Pytest E2E 043 Owner",
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(ownerEmail);
  grantBillingAccess(ownerEmail);
  const { access_token: token } = await signup.json();
  const authHeaders = { Authorization: `Bearer ${token}` };

  const customerRes = await api.post("/api/v1/customers", {
    headers: authHeaders,
    data: { name: customerName },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customer = await customerRes.json();

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });

  return { api, authHeaders, customer, ownerEmail, ownerPassword };
}

/** A General Building project with a real base contract: a general quote,
 * approved and handed off, through the real API (same payload shape as
 * e2e/general-quoting.spec.ts). Returns the project id and its known
 * base contract value. */
async function createHandedOffProject(
  api: APIRequestContext,
  authHeaders: Record<string, string>,
  customerId: string,
  runId: string,
  totalValue: number
): Promise<{ projectId: string; quoteId: string }> {
  const quoteRes = await api.post("/api/v1/quotes", {
    headers: authHeaders,
    data: {
      title: `Extension build ${runId}`,
      trade: "general_building",
      customer_id: customerId,
      lines: [{ description: "Build works", quantity: 1, unit: "job", unit_price: totalValue / 1.2 }],
    },
  });
  expect(quoteRes.ok()).toBeTruthy();
  const quote = await quoteRes.json();

  const approveRes = await api.post(`/api/v1/quotes/${quote.id}/approve`, { headers: authHeaders });
  expect(approveRes.ok()).toBeTruthy();

  const handoffRes = await api.post(`/api/v1/quotes/${quote.id}/handoff`, { headers: authHeaders });
  expect(handoffRes.ok()).toBeTruthy();
  const project = await handoffRes.json();

  return { projectId: project.id, quoteId: quote.id };
}

// ---- Journey A: Construction Project Financials ----
test("a_general_building_projects_financials_tab_rolls_up_costs_by_state", async ({ page }) => {
  const runId = uniqueRunId("journey-a");
  const { api, authHeaders, customer } = await signUpAndLogIn(page, runId);
  const { projectId } = await createHandedOffProject(api, authHeaders, customer.id, runId, 24000);

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Financials" }).click();

  await expect(page.getByText("£24,000").first()).toBeVisible();
  await expect(page.getByText("No costs recorded yet")).toBeVisible();

  // Budgeted material cost
  await page.getByRole("button", { name: /add cost/i }).click();
  await page.getByLabel("Description").fill("Quartz worktop supply");
  await page.getByLabel("Category").selectOption("material");
  await page.getByLabel("State").selectOption("budgeted");
  await page.getByLabel("Total cost").fill("6000");
  await page.getByRole("button", { name: /save cost/i }).click();
  await expect(page.getByText("Quartz worktop supply")).toBeVisible();

  // Committed subcontractor cost
  await page.getByRole("button", { name: /add cost/i }).click();
  await page.getByLabel("Description").fill("Groundworks subcontractor");
  await page.getByLabel("Category").selectOption("subcontractor");
  await page.getByLabel("State").selectOption("committed");
  await page.getByLabel("Total cost").fill("5000");
  await page.getByRole("button", { name: /save cost/i }).click();
  await expect(page.getByText("Groundworks subcontractor")).toBeVisible();

  // Actual labour cost
  await page.getByRole("button", { name: /add cost/i }).click();
  await page.getByLabel("Description").fill("Site team labour");
  await page.getByLabel("Category").selectOption("labour");
  await page.getByLabel("State").selectOption("actual");
  await page.getByLabel("Total cost").fill("4000");
  await page.getByRole("button", { name: /save cost/i }).click();
  await expect(page.getByText("Site team labour")).toBeVisible();

  // Forecast cost = 6000 + 5000 + 4000 = 15000
  await expect(page.getByText("£15,000")).toBeVisible();

  // Verify through the real API — never trust the UI alone for the
  // commercial figure.
  const summaryRes = await api.get(`/api/v1/projects/${projectId}/financials/summary`, {
    headers: authHeaders,
  });
  expect(summaryRes.ok()).toBeTruthy();
  const summary = await summaryRes.json();
  expect(summary.costs.budgeted_cost).toBe(6000);
  expect(summary.costs.committed_cost).toBe(5000);
  expect(summary.costs.actual_cost).toBe(4000);
  expect(summary.costs.forecast_cost).toBe(15000);
  expect(summary.contract.base_contract_value).toBe(24000);

  await api.dispose();
});

// ---- Journey B + C: Variation lifecycle + approval idempotency ----
test("approving_a_variation_increases_the_current_contract_exactly_once", async ({ page }) => {
  const runId = uniqueRunId("journey-bc");
  const { api, authHeaders, customer } = await signUpAndLogIn(page, runId);
  const { projectId } = await createHandedOffProject(api, authHeaders, customer.id, runId, 20000);

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Variations" }).click();
  await expect(page.getByText("No variations yet")).toBeVisible();

  await page.getByRole("button", { name: /new variation/i }).click();
  await page.getByLabel("Title").fill("Additional bathroom tiling");
  await page.getByLabel("Item description").fill("Extra floor tiles");
  await page.getByLabel("Quantity").fill("20");
  await page.getByLabel("Unit price").fill("15");
  await page.getByRole("button", { name: /save draft/i }).click();

  await expect(page.getByText(/V-001/)).toBeVisible();
  await expect(page.getByText("Draft")).toBeVisible();

  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Sent")).toBeVisible();

  const approveButton = page.getByRole("button", { name: "Approve" });
  await approveButton.click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();
  // Terminal status — Approve/Reject/Void are no longer offered, so a
  // second click through the UI is not even possible (Task 24's
  // immutability contract enforced visually, not just server-side).
  await expect(page.getByRole("button", { name: "Approve" })).not.toBeVisible();

  const summaryAfterFirstApproval = await (
    await api.get(`/api/v1/projects/${projectId}/financials/summary`, { headers: authHeaders })
  ).json();
  // 20 x £15 = £300 subtotal, +20% VAT = £360.
  expect(summaryAfterFirstApproval.contract.approved_variations_total).toBe(360);
  expect(summaryAfterFirstApproval.contract.current_contract_value).toBe(20360);

  // ---- Journey C: retry the approval directly against the API — the
  // exact regression this sprint's contract calls out by name. A second
  // approval of the same variation must never double the contract. ----
  const listRes = await api.get(`/api/v1/projects/${projectId}/variations`, { headers: authHeaders });
  const [variation] = await listRes.json();
  const retryRes = await api.post(`/api/v1/variations/${variation.id}/approve`, { headers: authHeaders });
  expect(retryRes.ok()).toBeTruthy();

  const summaryAfterRetry = await (
    await api.get(`/api/v1/projects/${projectId}/financials/summary`, { headers: authHeaders })
  ).json();
  expect(summaryAfterRetry.contract.approved_variations_total).toBe(360);
  expect(summaryAfterRetry.contract.current_contract_value).toBe(20360);

  await page.reload();
  await page.getByRole("tab", { name: "Financials" }).click();
  await expect(page.getByText("£20,360")).toBeVisible();

  await api.dispose();
});

// ---- Journey D: Margin / profitability recalculation ----
test("forecast_profit_and_margin_recalculate_as_costs_are_added", async ({ page }) => {
  const runId = uniqueRunId("journey-d");
  const { api, authHeaders, customer } = await signUpAndLogIn(page, runId);
  const { projectId } = await createHandedOffProject(api, authHeaders, customer.id, runId, 20000);

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Financials" }).click();

  // No costs yet — no confident forecast should be shown.
  await expect(page.getByText("No costs recorded yet")).toBeVisible();

  await page.getByRole("button", { name: /add cost/i }).click();
  await page.getByLabel("Description").fill("Initial materials");
  await page.getByLabel("Category").selectOption("material");
  await page.getByLabel("State").selectOption("actual");
  await page.getByLabel("Total cost").fill("10000");
  await page.getByRole("button", { name: /save cost/i }).click();

  // Forecast profit = 20000 - 10000 = 10000; margin = 50% (forecast and
  // actual coincide here, since the only cost recorded is itself actual).
  await expect(page.getByText("£10,000").first()).toBeVisible();
  await expect(page.getByText("50.0%").first()).toBeVisible();

  // Add a further cost that pushes margin below the risk threshold.
  await page.getByRole("button", { name: /add cost/i }).click();
  await page.getByLabel("Description").fill("Unexpected remedial works");
  await page.getByLabel("Category").selectOption("other");
  await page.getByLabel("State").selectOption("actual");
  await page.getByLabel("Total cost").fill("8500");
  await page.getByRole("button", { name: /save cost/i }).click();

  // Forecast cost now 18500; profit 1500; margin 7.5% — below the 15%
  // conservative default, so the margin-risk badge appears.
  await expect(page.getByText("Margin risk")).toBeVisible();

  const summaryRes = await api.get(`/api/v1/projects/${projectId}/financials/summary`, {
    headers: authHeaders,
  });
  const summary = await summaryRes.json();
  expect(summary.profitability.forecast_gross_profit).toBe(1500);
  expect(summary.profitability.margin_risk).toBe(true);

  await api.dispose();
});

// ---- Journey E: Tenant isolation ----
test("a_second_tenant_cannot_read_the_first_tenants_project_financials", async ({ page }) => {
  const runId = uniqueRunId("journey-e");
  const { api, authHeaders, customer } = await signUpAndLogIn(page, runId);
  const { projectId } = await createHandedOffProject(api, authHeaders, customer.id, runId, 15000);

  // Add a cost, so there is something to leak if isolation is broken.
  await api.post(`/api/v1/projects/${projectId}/costs`, {
    headers: authHeaders,
    data: { description: "Tenant A confidential cost", category: "other", state: "actual", total_cost: 500 },
  });

  const runIdB = uniqueRunId("journey-e-b");
  const ownerEmailB = `pytest-e2e-043-${runIdB}@example.invalid`;
  const ownerPasswordB = `Pytest-E2e-043-Password-${runIdB}!`;
  const signupB = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 043 Co ${runIdB}`,
      name: "Pytest E2E 043 Owner B",
      email: ownerEmailB,
      password: ownerPasswordB,
    },
  });
  expect(signupB.ok()).toBeTruthy();
  markVerified(ownerEmailB);
  grantBillingAccess(ownerEmailB);
  const { access_token: tokenB } = await signupB.json();
  const authHeadersB = { Authorization: `Bearer ${tokenB}` };

  // ---- Tenant B, through the real API ----
  const summaryResB = await api.get(`/api/v1/projects/${projectId}/financials/summary`, {
    headers: authHeadersB,
  });
  expect(summaryResB.status()).toBe(404);

  const costsResB = await api.get(`/api/v1/projects/${projectId}/costs`, { headers: authHeadersB });
  expect(costsResB.status()).toBe(404);

  // ---- Tenant B, through the real browser — the project itself 404s,
  // so the Financials tab (and Tenant A's cost data) is never reached. ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmailB);
  await page.getByLabel("Password").fill(ownerPasswordB);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Project not found.")).toBeVisible();
  await expect(page.getByText("Tenant A confidential cost")).not.toBeVisible();

  await api.dispose();
});

// ---- Journey F: Stone quote regression ----
test("a_stone_catalogue_quote_still_reaches_project_360_financials_unaffected", async ({ page }) => {
  const runId = uniqueRunId("journey-f");
  const { api, authHeaders, customer } = await signUpAndLogIn(page, runId);

  const quoteRes = await api.post("/api/v1/quote", {
    headers: authHeaders,
    data: {
      customer: customer.name,
      customer_id: customer.id,
      material: "Calacatta Gold",
      thickness: "20mm",
      kitchen_length: 3,
      postcode: `E2E-043-${runId}`,
    },
  });
  expect(quoteRes.ok()).toBeTruthy();
  const quote = await quoteRes.json();

  const approveRes = await api.post(`/api/v1/quotes/${quote.id}/approve`, { headers: authHeaders });
  expect(approveRes.ok()).toBeTruthy();
  const handoffRes = await api.post(`/api/v1/quotes/${quote.id}/handoff`, { headers: authHeaders });
  expect(handoffRes.ok()).toBeTruthy();
  const project = await handoffRes.json();

  await page.goto(`/projects/${project.id}`);
  await page.waitForLoadState("networkidle");
  // The stone catalogue/quote flow itself is untouched — confirmed by
  // reaching the ordinary Project 360 header.
  await expect(page.getByText("Enquiry", { exact: true }).first()).toBeVisible();

  await page.getByRole("tab", { name: "Financials" }).click();
  await expect(page.getByText("Contract Summary")).toBeVisible();

  const summaryRes = await api.get(`/api/v1/projects/${project.id}/financials/summary`, {
    headers: authHeaders,
  });
  expect(summaryRes.ok()).toBeTruthy();
  const summary = await summaryRes.json();
  expect(summary.contract.base_contract_source).toBe("approved_quote");
  expect(summary.contract.base_contract_value).toBeGreaterThan(0);

  await api.dispose();
});
