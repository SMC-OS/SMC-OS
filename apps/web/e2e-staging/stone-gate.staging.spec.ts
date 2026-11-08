import { expect, request, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

import { STAGING_API_URL } from "../playwright.staging.config";

/**
 * STONE-GATE (g1–g4) and DEF-003 (d1–d9) acceptance on a deployed staging
 * build, through the real browser and a pre-provisioned synthetic owner.
 * Every test makes its own Stone project, so runs never share state. The
 * test title names the checklist items it is evidence for.
 */

const OWNER_EMAIL = process.env.STAGING_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.STAGING_OWNER_PASSWORD ?? "";
const STAGES_TO_TEMPLATE = [
  "Measure / Site Visit",
  "Quote",
  "Approved",
  "Deposit",
  "Material Ordered / Reserved",
  "Template",
];

test.beforeAll(() => {
  if (!OWNER_EMAIL.endsWith(".invalid") || !OWNER_PASSWORD) {
    throw new Error("STAGING_OWNER_EMAIL (a .invalid synthetic owner) and STAGING_OWNER_PASSWORD are required");
  }
});

function runId(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

async function apiAs(email: string, password: string): Promise<APIRequestContext> {
  const anon = await request.newContext({ baseURL: STAGING_API_URL });
  const login = await anon.post("/api/v1/auth/login", { data: { email, password } });
  expect(login.status(), "API login").toBe(200);
  const { access_token: token } = await login.json();
  await anon.dispose();
  return request.newContext({ baseURL: STAGING_API_URL, extraHTTPHeaders: { Authorization: `Bearer ${token}` } });
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function newStoneProject(api: APIRequestContext, label: string): Promise<string> {
  const res = await api.post("/api/v1/projects", { data: { name: `Stone-gate ${label}`, project_type: "stone" } });
  expect(res.ok(), await res.text()).toBeTruthy();
  return (await res.json()).id;
}

async function openMaterials(page: Page, projectId: string) {
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: "Materials" }).click();
}

async function addRequirementInUi(page: Page, description: string, quantity: string, unit: string) {
  await page.getByRole("button", { name: /add requirement/i }).click();
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Quantity").fill(quantity);
  await page.getByLabel("Unit", { exact: true }).fill(unit);
  await page.getByRole("button", { name: /save requirement/i }).click();
  await expect(page.getByText(description).first()).toBeVisible();
}

/** Creates, approves and orders a one-line PO entirely in the UI. */
async function orderPoInUi(
  page: Page,
  line: { description: string; quantity: string; unit: string; cost: string; requirement?: string }
) {
  await page.getByRole("button", { name: /new purchase order/i }).click();
  if (line.requirement) {
    await page.getByLabel("Requirement for item 1").selectOption({ label: line.requirement });
  }
  await page.getByLabel("Item description").fill(line.description);
  await page.getByLabel("Quantity").fill(line.quantity);
  await page.getByLabel("Unit", { exact: true }).fill(line.unit);
  await page.getByLabel("Unit cost").fill(line.cost);
  await page.getByRole("button", { name: /save draft/i }).click();
  await page.getByRole("button", { name: "Approve" }).click();
  await page.getByRole("button", { name: /mark as ordered/i }).click();
  await page.getByRole("button", { name: /confirm order/i }).click();
  await expect(page.getByText("Ordered", { exact: true }).first()).toBeVisible();
}

async function deliverInUi(page: Page, quantity?: string) {
  await page.getByRole("button", { name: /record delivery/i }).click();
  if (quantity) await page.getByLabel("Receiving now").fill(quantity);
  const saved = page.waitForResponse(
    (res) => /\/receipts$/.test(res.url()) && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: /save delivery/i }).click();
  return saved;
}

async function requirementStatus(api: APIRequestContext, projectId: string, description: string) {
  const rows = await (await api.get(`/api/v1/projects/${projectId}/requirements`)).json();
  return rows.find((r: { description: string }) => r.description === description)?.status;
}

async function gateAtTemplate(page: Page, projectId: string) {
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /workflow/i }).click();
  // Every test starts a fresh project at the first stage, so each move must
  // appear in turn; waiting for it (never skipping) keeps the walk honest.
  for (const stage of STAGES_TO_TEMPLATE) {
    const move = page.getByRole("button", { name: `Move to ${stage}` });
    await expect(move).toBeVisible();
    const done = page.waitForResponse(
      (res) => res.url().endsWith(`/projects/${projectId}/workflow/transition`) && res.request().method() === "POST"
    );
    await move.click();
    await done;
  }
  return page.getByRole("button", { name: "Move to Fabrication" });
}

async function reloadGate(page: Page) {
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /workflow/i }).click();
  return page.getByRole("button", { name: "Move to Fabrication" });
}

test("g1 g2 g3 g4 d1 d3 d4: UI-linked line, full delivery, gate opens only then", async ({ page }) => {
  const id = runId("linked");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);

  const fabrication = await gateAtTemplate(page, projectId);
  await expect(fabrication).toBeEnabled(); // no requirements yet: existing contract, unblocked

  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Calacatta 20mm ${id}`, "2", "slab");
  await orderPoInUi(page, { description: "Calacatta slab", quantity: "2", unit: "slab", cost: "650",
                           requirement: `Calacatta 20mm ${id}` });
  expect(await requirementStatus(api, projectId, `Calacatta 20mm ${id}`)).toBe("ordered");

  let gate = await reloadGate(page);
  await expect(page.getByText(/materials have not all been received/i)).toBeVisible();
  await expect(gate).toBeDisabled();

  await openMaterials(page, projectId);
  expect((await deliverInUi(page)).status()).toBe(201);
  expect(await requirementStatus(api, projectId, `Calacatta 20mm ${id}`)).toBe("received");

  gate = await reloadGate(page);
  await expect(gate).toBeEnabled();
  await gate.click();
  await expect(page.getByText("Fabrication", { exact: true }).first()).toBeVisible();
  await api.dispose();
});

test("g1 d1 (reported symptom): unlinked UI line delivered, gate stays shut until linked in the UI", async ({ page }) => {
  const id = runId("unlinked");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);
  await gateAtTemplate(page, projectId);

  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Quartz 30mm ${id}`, "1", "slab");
  await orderPoInUi(page, { description: "Quartz slab", quantity: "1", unit: "slab", cost: "400" });
  await expect(page.getByText(/isn.t linked to a requirement/i)).toBeVisible();
  expect((await deliverInUi(page)).status()).toBe(201);
  expect(await requirementStatus(api, projectId, `Quartz 30mm ${id}`)).toBe("required");
  await expect(await reloadGate(page)).toBeDisabled();

  await openMaterials(page, projectId);
  const linked = page.waitForResponse((res) => res.url().includes("/link-requirement"));
  await page.getByLabel(/link .* to a requirement/i).selectOption({ label: `Quartz 30mm ${id}` });
  expect((await linked).status()).toBe(200);
  expect(await requirementStatus(api, projectId, `Quartz 30mm ${id}`)).toBe("received");
  await expect(await reloadGate(page)).toBeEnabled();
  await api.dispose();
});

test("d2 stone-partial: a part delivery keeps the gate shut; the balance opens it", async ({ page }) => {
  const id = runId("partial");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);
  await gateAtTemplate(page, projectId);
  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Granite ${id}`, "3", "slab");
  await orderPoInUi(page, { description: "Granite slab", quantity: "3", unit: "slab", cost: "300",
                           requirement: `Granite ${id}` });

  expect((await deliverInUi(page, "1")).status()).toBe(201);
  expect(await requirementStatus(api, projectId, `Granite ${id}`)).toBe("partially_received");
  await expect(await reloadGate(page)).toBeDisabled();

  await openMaterials(page, projectId);
  expect((await deliverInUi(page, "2")).status()).toBe(201);
  expect(await requirementStatus(api, projectId, `Granite ${id}`)).toBe("received");
  await expect(await reloadGate(page)).toBeEnabled();
  await api.dispose();
});

test("d2 short order: receiving everything ordered but less than required keeps the gate shut", async ({ page }) => {
  const id = runId("short");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);
  await gateAtTemplate(page, projectId);
  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Marble ${id}`, "3", "slab");
  await orderPoInUi(page, { description: "Marble slab", quantity: "2", unit: "slab", cost: "500",
                           requirement: `Marble ${id}` });
  expect((await deliverInUi(page)).status()).toBe(201);
  expect(await requirementStatus(api, projectId, `Marble ${id}`)).toBe("partially_received");
  await expect(await reloadGate(page)).toBeDisabled();
  await api.dispose();
});

test("d6: over-receipt is refused in the UI and changes nothing", async ({ page }) => {
  const id = runId("over");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);
  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Onyx ${id}`, "2", "slab");
  await orderPoInUi(page, { description: "Onyx slab", quantity: "2", unit: "slab", cost: "900",
                           requirement: `Onyx ${id}` });
  expect((await deliverInUi(page, "3")).status()).toBe(409);
  await expect(page.getByText(/receive more than was ordered/i)).toBeVisible();
  expect(await requirementStatus(api, projectId, `Onyx ${id}`)).toBe("ordered");
  await api.dispose();
});

test("d5 d9: a retried delivery is recorded once and cost moves committed to actual once", async ({ page }) => {
  const id = runId("retry");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);
  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Slate ${id}`, "2", "slab");
  await orderPoInUi(page, { description: "Slate slab", quantity: "2", unit: "slab", cost: "250",
                           requirement: `Slate ${id}` });
  const [po] = await (await api.get(`/api/v1/purchase-orders?project_id=${projectId}`)).json();
  const before = (await (await api.get(`/api/v1/projects/${projectId}/financials/summary`)).json()).costs;
  expect(before.committed_cost).toBe(500);

  const body = {
    received_at: new Date().toISOString(),
    idempotency_key: `staging-retry-${id}`,
    items: [{ purchase_order_item_id: po.items[0].id, quantity_received: 2 }],
  };
  const first = await api.post(`/api/v1/purchase-orders/${po.id}/receipts`, { data: body });
  const retry = await api.post(`/api/v1/purchase-orders/${po.id}/receipts`, { data: body });
  expect(first.status()).toBe(201);
  expect(retry.status()).toBe(201);
  expect((await retry.json()).id).toBe((await first.json()).id);
  expect(await (await api.get(`/api/v1/purchase-orders/${po.id}/receipts`)).json()).toHaveLength(1);

  const after = (await (await api.get(`/api/v1/projects/${projectId}/financials/summary`)).json()).costs;
  expect(after.committed_cost).toBe(0);
  expect(after.actual_cost).toBe(500);
  expect(after.cost_entry_count).toBe(1);
  await api.dispose();
});

test("d7: cancelling the only PO releases the requirement and refuses later deliveries", async ({ page }) => {
  const id = runId("cancel");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const projectId = await newStoneProject(api, id);
  await signIn(page);
  await openMaterials(page, projectId);
  await addRequirementInUi(page, `Basalt ${id}`, "1", "slab");
  await orderPoInUi(page, { description: "Basalt slab", quantity: "1", unit: "slab", cost: "350",
                           requirement: `Basalt ${id}` });
  const [po] = await (await api.get(`/api/v1/purchase-orders?project_id=${projectId}`)).json();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: `Cancel ${po.reference}` }).click();
  await expect(page.getByText("Cancelled", { exact: true }).first()).toBeVisible();
  expect(await requirementStatus(api, projectId, `Basalt ${id}`)).toBe("required");
  const late = await api.post(`/api/v1/purchase-orders/${po.id}/receipts`, {
    data: { received_at: new Date().toISOString(), items: [{ purchase_order_item_id: po.items[0].id, quantity_received: 1 }] },
  });
  expect(late.status()).toBe(409);
  await api.dispose();
});

test("d8: another workspace cannot read, receive or link on this PO", async () => {
  const otherEmail = process.env.STAGING_OTHER_OWNER_EMAIL ?? "";
  const otherPassword = process.env.STAGING_OTHER_OWNER_PASSWORD ?? "";
  test.skip(!otherEmail || !otherPassword, "needs a second provisioned synthetic owner; d8 stays unverified");
  const id = runId("isolation");
  const api = await apiAs(OWNER_EMAIL, OWNER_PASSWORD);
  const intruder = await apiAs(otherEmail, otherPassword);
  const projectId = await newStoneProject(api, id);
  const requirement = await (
    await api.post(`/api/v1/projects/${projectId}/requirements`, { data: { description: `Iso ${id}`, required_quantity: 1 } })
  ).json();
  const po = await (
    await api.post("/api/v1/purchase-orders", {
      data: { project_id: projectId, items: [{ description: "Iso slab", quantity: 1, unit_cost: 1 }] },
    })
  ).json();
  expect((await intruder.get(`/api/v1/purchase-orders/${po.id}`)).status()).toBe(404);
  expect((await intruder.get(`/api/v1/projects/${projectId}/requirements`)).status()).toBe(404);
  expect(
    (await intruder.post(`/api/v1/purchase-orders/${po.id}/items/${po.items[0].id}/link-requirement`, {
      data: { material_requirement_id: requirement.id },
    })).status()
  ).toBe(404);
  expect(
    (await intruder.post(`/api/v1/purchase-orders/${po.id}/receipts`, {
      data: { received_at: new Date().toISOString(), items: [{ purchase_order_item_id: po.items[0].id, quantity_received: 1 }] },
    })).status()
  ).toBe(404);
  await api.dispose();
  await intruder.dispose();
});
