import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * Sprint 042 (GeoCore Premium OS Plan 03) — Master Materials & Supplier
 * Catalogue + Stone Quote Engine V2, through the real browser against
 * the real Next.js app and real FastAPI server.
 *
 * Five journeys, matching the Plan 03 acceptance criteria:
 *   A. search -> select a catalogued surface -> quote -> reopen, and the
 *      commercial snapshot on that quote never changes even after the
 *      tenant's own catalogue price does (Task 7's immutability contract).
 *   B. a tenant sets their own price on a surface that has none, and a
 *      new quote reflects it.
 *   C. a custom material, saved to the tenant's private catalogue, is
 *      immediately reusable from search.
 *   D. Tenant A's private surface and pricing are invisible to Tenant B.
 *   E. construction (general) quoting is untouched by any of the above —
 *      no catalogue involvement, in the same session as a stone
 *      catalogue quote.
 *
 * Every fixture seeds its own catalogue data through the real
 * POST /catalogue/custom-materials + PUT .../override endpoints rather
 * than depending on app/catalogue/seed.py having been run against this
 * database — the same "don't depend on unrelated setup" posture as the
 * rest of this suite.
 */

function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: import("@playwright/test").Page, runId: string) {
  const companyName = `Pytest E2E Sprint 042 Co ${runId}`;
  const ownerEmail = `pytest-e2e-sprint042-${runId}@example.invalid`;
  const ownerPassword = `Pytest-E2e-Sprint042-Password-${runId}!`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: companyName,
      name: "Pytest E2E Owner",
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

  return { api, authHeaders, ownerEmail };
}

test("A_stone_catalogue_quote_prices_from_the_surface_and_its_snapshot_survives_a_later_price_change", async ({
  page,
}) => {
  const runId = uniqueRunId("journey-a");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const materialName = `Journey A Calacatta ${runId}`;

  // ---- Seed a priced, tenant-catalogued surface through the real API ----
  const customMaterial = await api.post("/api/v1/catalogue/custom-materials", {
    headers: authHeaders,
    data: {
      canonical_name: materialName,
      material_family: "quartz",
      variant: { thickness_mm: 20, finish: "Polished", slab_length_mm: 3200, slab_width_mm: 1600 },
      buy_cost_per_slab: 800,
      selling_price_per_slab: 1200,
      save_to_catalogue: true,
    },
  });
  expect(customMaterial.ok()).toBeTruthy();
  const { surface_id: surfaceId } = await customMaterial.json();

  // ---- Search the catalogue and select the surface ----
  await page.goto("/catalogue");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Search", { exact: true }).fill(materialName);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByText(materialName, { exact: true }).click();
  await expect(page.getByRole("heading", { name: materialName })).toBeVisible();
  await expect(page.getByText("£1,200")).toBeVisible();

  await page.getByRole("button", { name: "Use in a stone quote" }).click();
  await page.waitForURL(/\/quotes\/new\/stone\?/);

  // ---- The stone quote form is pre-filled from the catalogue ----
  await expect(page.getByText("From catalogue")).toBeVisible();
  await expect(page.getByText(materialName)).toBeVisible();
  await expect(page.getByText("20mm")).toBeVisible();

  await page.getByLabel("Customer name").fill(`Journey A Customer ${runId}`);
  await page.getByLabel("Length (mm)").fill("2400");

  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const created = await (await quoteCreated).json();

  expect(created.items[0].catalogue_surface_id).toBe(surfaceId);
  expect(created.items[0].price_per_slab).toBe(1200);
  const originalLineTotal = created.items[0].line_total as number;
  expect(originalLineTotal).toBeGreaterThan(0);

  // ---- Reopen the quote: the same price is shown ----
  await page.goto(`/quotes/${created.id}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(`£${originalLineTotal.toLocaleString("en-GB", { minimumFractionDigits: 2 })}`).first()).toBeVisible();

  // ---- Change the catalogue price AFTER the quote exists ----
  const overrideRes = await api.put(`/api/v1/catalogue/surfaces/${surfaceId}/override`, {
    headers: authHeaders,
    data: { selling_price_per_slab: 9999 },
  });
  expect(overrideRes.ok()).toBeTruthy();

  // ---- The already-created quote's price is unchanged (Task 7) ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(`£${originalLineTotal.toLocaleString("en-GB", { minimumFractionDigits: 2 })}`).first()).toBeVisible();
  await expect(page.getByText(/9,999/)).not.toBeVisible();

  const reopened = await api.get(`/api/v1/quotes/${created.id}`, { headers: authHeaders });
  const reopenedBody = await reopened.json();
  expect(reopenedBody.items[0].price_per_slab).toBe(1200);
  expect(reopenedBody.items[0].line_total).toBe(originalLineTotal);
});

test("B_a_tenant_can_set_their_own_price_and_a_new_quote_reflects_it", async ({ page }) => {
  const runId = uniqueRunId("journey-b");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const materialName = `Journey B Granite ${runId}`;

  // ---- Seed the surface with NO price at all ----
  const customMaterial = await api.post("/api/v1/catalogue/custom-materials", {
    headers: authHeaders,
    data: {
      canonical_name: materialName,
      material_family: "granite",
      variant: { thickness_mm: 30 },
      save_to_catalogue: true,
    },
  });
  expect(customMaterial.ok()).toBeTruthy();
  const { surface_id: surfaceId } = await customMaterial.json();

  await page.goto("/catalogue");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Search", { exact: true }).fill(materialName);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByText(materialName, { exact: true }).click();

  // ---- Never fabricated: no price shown yet ----
  await expect(page.getByText(/No price set yet/)).toBeVisible();

  // ---- Set a price through the UI ----
  await page.getByRole("button", { name: "Set your price" }).click();
  await page.getByLabel("Your buy cost per slab").fill("700");
  await page.getByLabel("Your markup (%)").fill("25");
  await page.getByRole("button", { name: "Save price" }).click();

  // 700 * 1.25 = 875.
  await expect(page.getByText("£875")).toBeVisible();

  // ---- A new quote uses that price ----
  await page.getByRole("button", { name: "Use in a stone quote" }).click();
  await page.waitForURL(/\/quotes\/new\/stone\?/);
  await page.getByLabel("Customer name").fill(`Journey B Customer ${runId}`);
  await page.getByLabel("Length (mm)").fill("2000");

  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const created = await (await quoteCreated).json();

  expect(created.items[0].catalogue_surface_id).toBe(surfaceId);
  expect(created.items[0].price_per_slab).toBe(875);
});

test("C_a_custom_material_saved_to_the_catalogue_is_immediately_reusable_from_search", async ({
  page,
}) => {
  const runId = uniqueRunId("journey-c");
  await signUpAndLogIn(page, runId);
  const materialName = `Journey C Verde Alpi ${runId}`;

  await page.goto("/catalogue");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Can't find your stone? Add custom material" }).click();

  // Scoped to the custom-material form: its own "Material family" select
  // shares a label with the search filter's, which is still on screen.
  const customForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Add material" }) });
  await customForm.getByLabel("Material name").fill(materialName);
  await customForm.getByLabel("Material family").selectOption("granite");
  await customForm.getByLabel("Thickness (mm)").fill("20");
  await customForm.getByLabel("Your buy cost per slab").fill("500");
  await customForm.getByLabel("Your selling price per slab").fill("750");
  // "Save to my private catalogue" is checked by default.
  await customForm.getByRole("button", { name: "Add material" }).click();

  await expect(page.getByText(/has been saved to your private catalogue/)).toBeVisible();

  // ---- Immediately reusable from a fresh search ----
  await page.getByRole("button", { name: "Use in a stone quote" }).click();
  await page.waitForURL(/\/quotes\/new\/stone\?/);
  await expect(page.getByText("From catalogue")).toBeVisible();

  await page.getByLabel("Customer name").fill(`Journey C Customer ${runId}`);
  await page.getByLabel("Length (mm)").fill("1800");

  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const created = await (await quoteCreated).json();
  expect(created.items[0].catalogue_surface_id).toBeTruthy();
  expect(created.items[0].price_per_slab).toBe(750);

  // ---- And it now shows up in an ordinary search, unprompted ----
  await page.goto("/catalogue");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Search", { exact: true }).fill(materialName);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(materialName, { exact: true })).toBeVisible();
  await expect(page.getByText("Your private catalogue")).toBeVisible();
});

test("D_tenant_isolation_a_private_surface_and_its_price_are_invisible_to_another_tenant", async ({
  page,
}) => {
  const runId = uniqueRunId("journey-d");
  const materialName = `Journey D Secret Onyx ${runId}`;

  const { api: apiA, authHeaders: headersA } = await signUpAndLogIn(page, `${runId}-a`);
  const customMaterial = await apiA.post("/api/v1/catalogue/custom-materials", {
    headers: headersA,
    data: {
      canonical_name: materialName,
      material_family: "onyx",
      buy_cost_per_slab: 2000,
      selling_price_per_slab: 3000,
      save_to_catalogue: true,
    },
  });
  expect(customMaterial.ok()).toBeTruthy();
  const { surface_id: surfaceId } = await customMaterial.json();

  // Fresh page/session for Tenant B — logging in again overwrites the
  // stored token, same as any other cross-tenant-boundary spec.
  const { api: apiB, authHeaders: headersB } = await signUpAndLogIn(page, `${runId}-b`);

  await page.goto("/catalogue");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Search", { exact: true }).fill(materialName);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  // Phase A — which empty state shows depends on whether this database
  // has global reference data loaded ("No surfaces found") or none at all
  // ("Your material catalogue is empty"); either way Tenant A's private
  // surface must not appear.
  await expect(
    page.getByText(/^(No surfaces found|Your material catalogue is empty)$/)
  ).toBeVisible();
  await expect(page.getByText(materialName, { exact: true })).not.toBeVisible();

  // Tenant A's private surface never counts towards Tenant B's catalogue.
  const statusRes = await apiB.get("/api/v1/catalogue/meta/status", { headers: headersB });
  expect(statusRes.ok()).toBeTruthy();
  expect((await statusRes.json()).tenant_surfaces).toBe(0);

  // Not reachable directly by id either, even knowing it.
  const directRes = await apiB.get(`/api/v1/catalogue/surfaces/${surfaceId}`, {
    headers: headersB,
  });
  expect(directRes.status()).toBe(404);

  await apiA.dispose();
  await apiB.dispose();
});

test("E_construction_quoting_is_untouched_alongside_a_stone_catalogue_quote_in_the_same_session", async ({
  page,
}) => {
  const runId = uniqueRunId("journey-e");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);

  // ---- A general construction quote — no catalogue anywhere ----
  await page.goto("/quotes/new");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Quote title").fill(`Electrical rewire, Journey E ${runId}`);
  await page.getByLabel("Type of work").selectOption("electrical");
  await page.getByLabel("Description").fill("First and second fix rewire");
  await page.getByLabel("Quantity").fill("1");
  await page.getByLabel("Unit").selectOption("item");
  await page.getByLabel("Rate (£)").fill("2400");

  const generalQuoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quotes") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: /create quote/i }).click();
  const generalQuote = await (await generalQuoteCreated).json();

  expect(generalQuote.quote_kind).toBe("general");
  expect(generalQuote.material).toBeNull();
  expect(generalQuote.items[0].line_kind).toBe("labour");
  expect(generalQuote.items[0].material).toBeNull();

  const generalDetail = await api.get(`/api/v1/quotes/${generalQuote.id}`, {
    headers: authHeaders,
  });
  const generalDetailBody = await generalDetail.json();
  expect(generalDetailBody.items[0].catalogue_surface_id ?? null).toBeNull();
  expect(generalDetailBody.items[0].catalogue_snapshot ?? null).toBeNull();

  // ---- A plain, non-catalogue stone quote in the same session still works ----
  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("From catalogue")).not.toBeVisible();
  await page.getByLabel("Customer name").fill(`Journey E Stone Customer ${runId}`);
  await page.getByLabel("Length (mm)").fill("2400");

  const stoneQuoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const stoneQuote = await (await stoneQuoteCreated).json();
  expect(stoneQuote.items[0].catalogue_surface_id ?? null).toBeNull();
  expect(stoneQuote.items[0].line_total).toBeGreaterThan(0);
});
