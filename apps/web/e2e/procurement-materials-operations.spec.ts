import { expect, request, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * GeoCore Premium OS Plan 05 (Sprint 044) — end-to-end coverage for the
 * Procurement + Materials Operations layer, through the real browser
 * against the real Next.js app and real FastAPI server. Journeys A-G
 * from the sprint contract:
 *   A. Stone Procurement — a requirement, a PO, approval, ordering and a
 *      full receipt on a Stone project's Materials tab.
 *   B. Construction Procurement — the same lifecycle on a General
 *      Building project, proving nothing here is stone-specific.
 *   C. Partial Delivery — two part-deliveries on one PO item reach
 *      "received" only once the full quantity has arrived.
 *   D. Over-Receipt Safety — receiving more than the outstanding
 *      quantity is rejected, and the already-received quantity is
 *      unchanged afterwards.
 *   E. Tenant Isolation — a second tenant gets a clean 404 on every
 *      procurement resource, no leak.
 *   F. Financial Integration — approving a PO creates a committed cost
 *      visible on Financials; a full receipt flips it to actual; a
 *      retried approval never creates a second cost entry.
 *   G. Workflow Gate — a Stone project cannot move Template -> Fabrication
 *      while a material requirement is still outstanding, and the move
 *      becomes available the moment it is fully received.
 */

function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: Page, runId: string) {
  const ownerEmail = `pytest-e2e-044-${runId}@example.invalid`;
  const ownerPassword = `Pytest-E2e-044-Password-${runId}!`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 044 Co ${runId}`,
      name: "Pytest E2E 044 Owner",
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(ownerEmail);
  grantBillingAccess(ownerEmail);
  const { access_token: token } = await signup.json();
  const authHeaders = { Authorization: `Bearer ${token}` };

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });

  return { api, authHeaders, ownerEmail, ownerPassword };
}

/** A bare project (no quote, no customer needed) of the given trade —
 * procurement is deliberately independent of a project having a
 * contract at all. */
async function createProject(
  api: APIRequestContext,
  authHeaders: Record<string, string>,
  runId: string,
  projectType: string,
  name: string
): Promise<string> {
  const res = await api.post("/api/v1/projects", {
    headers: authHeaders,
    data: { name: `${name} ${runId}`, project_type: projectType },
  });
  expect(res.ok()).toBeTruthy();
  const project = await res.json();
  return project.id;
}

// ---- Journey A: Stone Procurement ----
test("a_stone_projects_materials_tab_carries_a_requirement_through_to_a_full_receipt", async ({ page }) => {
  const runId = uniqueRunId("journey-a");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "stone", "Kitchen worktop job");

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Materials" }).click();

  // ---- Requirement ----
  await page.getByRole("button", { name: /add requirement/i }).click();
  await page.getByLabel("Description").fill("40mm Calacatta quartz slabs");
  await page.getByLabel("Quantity").fill("2");
  await page.getByLabel("Unit", { exact: true }).fill("slab");
  await page.getByRole("button", { name: /save requirement/i }).click();
  await expect(page.getByText("40mm Calacatta quartz slabs")).toBeVisible();
  await expect(page.getByText("Required")).toBeVisible();

  // ---- Purchase order ----
  await page.getByRole("button", { name: /new purchase order/i }).click();
  await page.getByLabel("Item description").fill("Calacatta quartz slab");
  await page.getByLabel("Quantity").fill("2");
  await page.getByLabel("Unit", { exact: true }).fill("slab");
  await page.getByLabel("Unit cost").fill("500");
  await page.getByRole("button", { name: /save draft/i }).click();
  await expect(page.getByText("PO-001")).toBeVisible();
  await expect(page.getByText("£1,200 total")).toBeVisible(); // £1000 + 20% VAT

  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /mark as ordered/i }).click();
  await page.getByRole("button", { name: /confirm order/i }).click();
  await expect(page.getByText("Ordered", { exact: true })).toBeVisible();

  // ---- Full receipt ----
  await page.getByRole("button", { name: /record delivery/i }).click();
  await page.getByRole("button", { name: /save delivery/i }).click();
  await expect(page.getByText("Received", { exact: true }).first()).toBeVisible();

  await api.dispose();
});

// ---- Journey B: Construction Procurement ----
test("a_general_building_projects_materials_tab_runs_the_same_lifecycle", async ({ page }) => {
  const runId = uniqueRunId("journey-b");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "general_building", "Rear extension");

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Materials" }).click();

  await page.getByRole("button", { name: /add requirement/i }).click();
  await page.getByLabel("Description").fill("Structural steel beams");
  await page.getByLabel("Quantity").fill("4");
  await page.getByLabel("Unit", { exact: true }).fill("item");
  await page.getByRole("button", { name: /save requirement/i }).click();
  await expect(page.getByText("Structural steel beams")).toBeVisible();

  await page.getByRole("button", { name: /new purchase order/i }).click();
  await page.getByLabel("Item description").fill("Steel I-beam");
  await page.getByLabel("Quantity").fill("4");
  await page.getByLabel("Unit", { exact: true }).fill("item");
  await page.getByLabel("Unit cost").fill("250");
  await page.getByRole("button", { name: /save draft/i }).click();
  await expect(page.getByText("PO-001")).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("button", { name: /mark as ordered/i }).click();
  await page.getByRole("button", { name: /confirm order/i }).click();
  await page.getByRole("button", { name: /record delivery/i }).click();
  await page.getByRole("button", { name: /save delivery/i }).click();
  await expect(page.getByText("Received", { exact: true }).first()).toBeVisible();

  await api.dispose();
});

// ---- Journey C: Partial Delivery ----
test("a_purchase_order_reaches_received_only_after_two_part_deliveries", async ({ page }) => {
  const runId = uniqueRunId("journey-c");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "stone", "Partial delivery job");

  const poRes = await api.post("/api/v1/purchase-orders", {
    headers: authHeaders,
    data: {
      project_id: projectId,
      items: [{ description: "Porcelain slabs", quantity: 10, unit: "slab", unit_cost: 100 }],
    },
  });
  expect(poRes.ok()).toBeTruthy();
  const po = await poRes.json();
  await api.post(`/api/v1/purchase-orders/${po.id}/approve`, { headers: authHeaders });
  await api.post(`/api/v1/purchase-orders/${po.id}/order`, { headers: authHeaders, data: {} });

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Materials" }).click();
  await expect(page.getByText("Ordered", { exact: true })).toBeVisible();

  // ---- First part-delivery: 4 of 10 ----
  await page.getByRole("button", { name: /record delivery/i }).click();
  await page.getByLabel("Receiving now").fill("4");
  await page.getByRole("button", { name: /save delivery/i }).click();
  await expect(page.getByText("Partially received", { exact: true }).first()).toBeVisible();

  // ---- Re-opening the delivery form proves the first part-delivery
  // really persisted (the form itself closes after each save, so this
  // is the real record, re-fetched from the backend, not a leftover). ----
  await page.getByRole("button", { name: /record delivery/i }).click();
  await expect(page.getByText("4 of 10 slab received")).toBeVisible();

  // ---- Second part-delivery: the remaining 6 ----
  // The "Receiving now" field defaults to the remaining quantity (6).
  await page.getByRole("button", { name: /save delivery/i }).click();
  await expect(page.getByText("Received", { exact: true }).first()).toBeVisible();

  const finalPo = await (
    await api.get(`/api/v1/purchase-orders/${po.id}`, { headers: authHeaders })
  ).json();
  expect(finalPo.status).toBe("received");
  expect(finalPo.items[0].quantity_received).toBe(10);

  await api.dispose();
});

// ---- Journey D: Over-Receipt Safety ----
test("receiving_more_than_was_ordered_is_rejected_and_changes_nothing", async ({ page }) => {
  const runId = uniqueRunId("journey-d");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "stone", "Over-receipt job");

  const poRes = await api.post("/api/v1/purchase-orders", {
    headers: authHeaders,
    data: {
      project_id: projectId,
      items: [{ description: "Granite slabs", quantity: 5, unit: "slab", unit_cost: 200 }],
    },
  });
  const po = await poRes.json();
  await api.post(`/api/v1/purchase-orders/${po.id}/approve`, { headers: authHeaders });
  await api.post(`/api/v1/purchase-orders/${po.id}/order`, { headers: authHeaders, data: {} });

  // ---- Reject directly through the real API — the exact regression
  // this sprint's contract calls out by name (never silently clamped). ----
  const overReceiptRes = await api.post(`/api/v1/purchase-orders/${po.id}/receipts`, {
    headers: authHeaders,
    data: {
      received_at: new Date().toISOString(),
      items: [{ purchase_order_item_id: po.items[0].id, quantity_received: 6 }],
    },
  });
  expect(overReceiptRes.status()).toBe(409);

  const afterRejection = await (
    await api.get(`/api/v1/purchase-orders/${po.id}`, { headers: authHeaders })
  ).json();
  expect(afterRejection.items[0].quantity_received).toBe(0);
  expect(afterRejection.status).toBe("ordered");

  // ---- Reject through the real Materials tab too ----
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Materials" }).click();
  await page.getByRole("button", { name: /record delivery/i }).click();
  await page.getByLabel("Receiving now").fill("6");
  await page.getByRole("button", { name: /save delivery/i }).click();
  await expect(page.getByText(/receive more than was ordered/i)).toBeVisible();

  const stillUnchanged = await (
    await api.get(`/api/v1/purchase-orders/${po.id}`, { headers: authHeaders })
  ).json();
  expect(stillUnchanged.items[0].quantity_received).toBe(0);

  await api.dispose();
});

// ---- Journey E: Tenant Isolation ----
test("a_second_tenant_cannot_read_the_first_tenants_procurement_data", async ({ page }) => {
  const runId = uniqueRunId("journey-e");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "stone", "Tenant A confidential job");

  const requirementRes = await api.post(`/api/v1/projects/${projectId}/requirements`, {
    headers: authHeaders,
    data: { description: "Tenant A confidential slab" },
  });
  expect(requirementRes.ok()).toBeTruthy();
  const requirement = await requirementRes.json();

  const poRes = await api.post("/api/v1/purchase-orders", {
    headers: authHeaders,
    data: { project_id: projectId, items: [{ description: "Slab", quantity: 1, unit: "slab", unit_cost: 500 }] },
  });
  const po = await poRes.json();

  const runIdB = uniqueRunId("journey-e-b");
  const ownerEmailB = `pytest-e2e-044-${runIdB}@example.invalid`;
  const ownerPasswordB = `Pytest-E2e-044-Password-${runIdB}!`;
  const signupB = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 044 Co ${runIdB}`,
      name: "Pytest E2E 044 Owner B",
      email: ownerEmailB,
      password: ownerPasswordB,
    },
  });
  expect(signupB.ok()).toBeTruthy();
  markVerified(ownerEmailB);
  grantBillingAccess(ownerEmailB);
  const { access_token: tokenB } = await signupB.json();
  const authHeadersB = { Authorization: `Bearer ${tokenB}` };

  // ---- Tenant B, through the real API — every procurement resource ----
  expect(
    (await api.get(`/api/v1/projects/${projectId}/requirements`, { headers: authHeadersB })).status()
  ).toBe(404);
  expect((await api.patch(`/api/v1/requirements/${requirement.id}`, { headers: authHeadersB, data: {} })).status()).toBe(
    404
  );
  expect((await api.get(`/api/v1/purchase-orders/${po.id}`, { headers: authHeadersB })).status()).toBe(404);
  expect(
    (
      await api.post(`/api/v1/purchase-orders/${po.id}/approve`, { headers: authHeadersB })
    ).status()
  ).toBe(404);

  // ---- Tenant B, through the real browser — the project itself 404s ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmailB);
  await page.getByLabel("Password").fill(ownerPasswordB);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Project not found.")).toBeVisible();
  await expect(page.getByText("Tenant A confidential slab")).not.toBeVisible();

  await api.dispose();
});

// ---- Journey F: Financial Integration ----
test("approving_and_receiving_a_purchase_order_moves_a_cost_from_committed_to_actual_exactly_once", async ({
  page,
}) => {
  const runId = uniqueRunId("journey-f");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "stone", "Financial integration job");

  const poRes = await api.post("/api/v1/purchase-orders", {
    headers: authHeaders,
    data: {
      project_id: projectId,
      items: [{ description: "Quartz slab", quantity: 1, unit: "slab", unit_cost: 1000 }],
    },
  });
  const po = await poRes.json();

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Materials" }).click();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();

  // ---- A committed cost of exactly £1,000 now appears on Financials —
  // the PO item's own line total (ex-VAT internal cost), never the PO's
  // £1,200 VAT-inclusive total (VAT belongs to customer pricing, not the
  // internal cost ledger). ----
  await page.getByRole("tab", { name: "Financials" }).click();
  await expect(page.getByText("£1,000").first()).toBeVisible();

  const summaryAfterApproval = await (
    await api.get(`/api/v1/projects/${projectId}/financials/summary`, { headers: authHeaders })
  ).json();
  expect(summaryAfterApproval.costs.committed_cost).toBe(1000);
  expect(summaryAfterApproval.costs.actual_cost).toBe(0);

  // ---- Retry the approval directly against the API — the exact
  // regression this sprint's contract calls out by name: a PO's cost
  // must never appear twice under a retried approval. ----
  const retryRes = await api.post(`/api/v1/purchase-orders/${po.id}/approve`, { headers: authHeaders });
  expect(retryRes.ok()).toBeTruthy();
  const afterRetry = await (
    await api.get(`/api/v1/projects/${projectId}/financials/summary`, { headers: authHeaders })
  ).json();
  expect(afterRetry.costs.committed_cost).toBe(1000);

  // ---- Order, then fully receive — the same cost entry flips to actual
  // in place, never creating a second row. ----
  await api.post(`/api/v1/purchase-orders/${po.id}/order`, { headers: authHeaders, data: {} });
  await api.post(`/api/v1/purchase-orders/${po.id}/receipts`, {
    headers: authHeaders,
    data: {
      received_at: new Date().toISOString(),
      items: [{ purchase_order_item_id: po.items[0].id, quantity_received: 1 }],
    },
  });

  const summaryAfterReceipt = await (
    await api.get(`/api/v1/projects/${projectId}/financials/summary`, { headers: authHeaders })
  ).json();
  expect(summaryAfterReceipt.costs.committed_cost).toBe(0);
  expect(summaryAfterReceipt.costs.actual_cost).toBe(1000);

  await page.reload();
  await page.getByRole("tab", { name: "Financials" }).click();
  await expect(page.getByText("£1,000").first()).toBeVisible();

  await api.dispose();
});

// ---- Journey G: Workflow Gate ----
test("a_stone_project_cannot_enter_fabrication_until_its_materials_are_received", async ({ page }) => {
  const runId = uniqueRunId("journey-g");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const projectId = await createProject(api, authHeaders, runId, "stone", "Gated fabrication job");

  const requirementRes = await api.post(`/api/v1/projects/${projectId}/requirements`, {
    headers: authHeaders,
    data: { description: "Worktop slab for fabrication" },
  });
  const requirement = await requirementRes.json();

  const poRes = await api.post("/api/v1/purchase-orders", {
    headers: authHeaders,
    data: {
      project_id: projectId,
      items: [
        {
          description: "Worktop slab",
          material_requirement_id: requirement.id,
          quantity: 1,
          unit: "slab",
          unit_cost: 400,
        },
      ],
    },
  });
  const po = await poRes.json();
  await api.post(`/api/v1/purchase-orders/${po.id}/approve`, { headers: authHeaders });
  await api.post(`/api/v1/purchase-orders/${po.id}/order`, { headers: authHeaders, data: {} });

  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /workflow/i }).click();

  // ---- Advance through Stone's real sequence up to Template ----
  for (const stageLabel of [
    "Measure / Site Visit",
    "Quote",
    "Approved",
    "Deposit",
    "Material Ordered / Reserved",
    "Template",
  ]) {
    const moveButton = page.getByRole("button", { name: `Move to ${stageLabel}` });
    await expect(moveButton).toBeVisible();
    const transitionResponse = page.waitForResponse(
      (res) =>
        res.url().endsWith(`/api/v1/projects/${projectId}/workflow/transition`) &&
        res.request().method() === "POST"
    );
    await moveButton.click();
    await transitionResponse;
  }
  await expect(page.getByText("Template", { exact: true }).first()).toBeVisible();

  // ---- Fabrication is blocked: the real materials_ready gate renders
  // its own reason, and the move button is present but disabled — never
  // hidden with the reason silently lost, and never enabled while
  // secretly rejecting the click server-side. ----
  await expect(page.getByText(/materials have not all been received/i)).toBeVisible();
  await expect(page.getByRole("button", { name: "Move to Fabrication" })).toBeDisabled();

  // ---- Fully receive the material ----
  await page.getByRole("tab", { name: "Materials" }).click();
  await page.getByRole("button", { name: /record delivery/i }).click();
  await page.getByRole("button", { name: /save delivery/i }).click();
  await expect(page.getByText("Received", { exact: true }).first()).toBeVisible();

  // ---- The gate clears and the move is now available. A reload is
  // needed here: each Project 360 tab loads its own data once on mount
  // (the same reason job-financials-variations.spec.ts reloads before
  // re-checking Financials after a Variations-tab change), so the
  // Workflow tab's gate evaluation only reflects the delivery just
  // recorded on the Materials tab once it re-fetches. ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /workflow/i }).click();
  const fabricationButton = page.getByRole("button", { name: "Move to Fabrication" });
  await expect(fabricationButton).toBeEnabled();
  const transitionResponse = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/projects/${projectId}/workflow/transition`) &&
      res.request().method() === "POST"
  );
  await fabricationButton.click();
  await transitionResponse;
  await expect(page.getByText("Fabrication", { exact: true }).first()).toBeVisible();

  await api.dispose();
});
