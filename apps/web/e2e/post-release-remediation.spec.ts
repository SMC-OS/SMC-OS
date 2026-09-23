import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";

/**
 * Post-release remediation (§3/§4) — through the real browser against
 * the real Next.js app and real FastAPI server.
 *
 *   A. the stone quote configurator's inline material search (not the
 *      separate /catalogue page) finds a catalogued surface by typing,
 *      links it, and submits the linkage.
 *   B. the visual layout picker and extras picker record their choice
 *      on the submitted item's notes and it appears in the itemized
 *      result.
 *
 * Follows the same "seed catalogue data through the real API, don't
 * depend on app/catalogue/seed.py having run" posture as
 * e2e/master-catalogue.spec.ts.
 */

function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: import("@playwright/test").Page, runId: string) {
  const companyName = `Pytest E2E Remediation Co ${runId}`;
  const ownerEmail = `pytest-e2e-remediation-${runId}@example.invalid`;
  const ownerPassword = `Pytest-E2e-Remediation-Password-${runId}!`;

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

test("A_inline_catalogue_material_search_on_the_stone_quote_page_finds_and_links_a_surface", async ({
  page,
}) => {
  const runId = uniqueRunId("remediation-a");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const materialName = `Remediation Journey A Marble ${runId}`;

  // Seed a real, searchable catalogue surface through the API — the
  // same fixture pattern master-catalogue.spec.ts already uses.
  const customMaterial = await api.post("/api/v1/catalogue/custom-materials", {
    headers: authHeaders,
    data: {
      canonical_name: materialName,
      material_family: "marble",
      variant: { thickness_mm: 20, finish: "Polished", slab_length_mm: 3200, slab_width_mm: 1600 },
      buy_cost_per_slab: 600,
      selling_price_per_slab: 900,
      save_to_catalogue: true,
    },
  });
  expect(customMaterial.ok()).toBeTruthy();
  const { surface_id: surfaceId } = await customMaterial.json();

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  // Type straight into the inline Material search on this page — never
  // navigating to /catalogue at all.
  await page.getByLabel("Material").fill(materialName);
  await page.getByRole("button", { name: new RegExp(materialName) }).click();

  await expect(page.getByText("From catalogue")).toBeVisible();

  await page.getByLabel("Customer name").fill(`Pytest Remediation Customer ${runId}`);
  await page.getByLabel("Length (mm)").first().fill("2400");

  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const created = await (await quoteCreated).json();

  await expect(page.getByRole("heading", { name: /quote for/i })).toBeVisible();
  expect(created.items[0].catalogue_surface_id).toBe(surfaceId);
  expect(created.items[0].material).toBe(materialName);
});

test("B_layout_and_extras_pickers_record_their_choice_on_the_itemised_result", async ({ page }) => {
  const runId = uniqueRunId("remediation-b");
  await signUpAndLogIn(page, runId);

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  await page.getByRole("radio", { name: "U-shape" }).click();
  // The checkbox itself is visually hidden (sr-only) — its <label> is the
  // real click target, same as everywhere else this pattern is used.
  await page.getByText("Sink / hob cutout").click();

  await page.getByLabel("Customer name").fill(`Pytest Layout Customer ${runId}`);
  await page.getByLabel("Length (mm)").first().fill("2400");
  await page.getByRole("button", { name: "Calculate Quote" }).click();

  // Assert on the itemised RESULT, not the form: the picker labels stay
  // on screen after calculating, so a bare getByText(/U-shape/) matched
  // the picker (passing without checking the result at all) or, once the
  // result rendered, two elements (a strict-mode failure). Wait for the
  // result heading, then match the exact notes line the quote records.
  await expect(
    page.getByRole("heading", { name: `Quote for Pytest Layout Customer ${runId}` })
  ).toBeVisible();
  await expect(page.getByText("Layout: U-shape. Extras: Sink / hob cutout", { exact: true })).toBeVisible();
});
