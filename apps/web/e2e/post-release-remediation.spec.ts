import { setStoneJobPrice } from "./stone-pricing-helper";
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

async function signUpAndLogIn(
  page: import("@playwright/test").Page,
  runId: string,
) {
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

  return { api, authHeaders, ownerEmail, ownerPassword };
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
      variant: {
        thickness_mm: 20,
        finish: "Polished",
        slab_length_mm: 3200,
        slab_width_mm: 1600,
      },
      buy_cost_per_slab: 600,
      selling_price_per_slab: 900,
      save_to_catalogue: true,
    },
  });
  expect(customMaterial.ok()).toBeTruthy();
  const { surface_id: surfaceId } = await customMaterial.json();
  const photoUrl = "https://example.com/synthetic-qa-marble.png";
  await page.route(photoUrl, (route) =>
    route.fulfill({
      status: 200,
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC",
        "base64",
      ),
    }),
  );
  const photoSaved = await api.put(
    `/api/v1/catalogue/surfaces/${surfaceId}/override`,
    {
      headers: authHeaders,
      data: { image_url: photoUrl, selling_price_per_slab: 900 },
    },
  );
  expect(photoSaved.ok()).toBeTruthy();

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  // Type straight into the inline Material search on this page — never
  // navigating to /catalogue at all.
  await page.getByLabel("Material", { exact: true }).fill(materialName);
  await expect(
    page.getByRole("img", { name: materialName, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("img", { name: materialName, exact: true }),
  ).toHaveJSProperty("naturalWidth", 1);
  await page.getByRole("button", { name: new RegExp(materialName) }).click();

  await expect(page.getByText("From catalogue")).toBeVisible();

  await page
    .getByLabel("Customer name")
    .fill(`Pytest Remediation Customer ${runId}`);
  await page
    .getByLabel("Customer address", { exact: true })
    .fill("1 Synthetic Street, London");
  await page.getByLabel("Postcode", { exact: true }).fill("NW2 7RP");
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if ((await material.isVisible()) && !(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  await page.getByRole("button", { name: "Next: Layout", exact: true }).click();
  await page.getByLabel("Length (mm)").first().fill("2400");

  const quoteCreated = page.waitForResponse(
    (res) =>
      res.url().endsWith("/api/v1/quote") && res.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Next: Design details", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Next: Pricing", exact: true })
    .click();
  await setStoneJobPrice(page);
  await page.getByRole("button", { name: "Next: Review", exact: true }).click();
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if (!(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  if (
    await page
      .getByLabel("Your job price before discount and VAT (£)")
      .isVisible()
  ) {
    if (
      !(await page
        .getByLabel("Your job price before discount and VAT (£)")
        .inputValue())
    )
      await setStoneJobPrice(page);
  }
  await page.getByRole("button", { name: "Save Quote" }).click();
  const created = await (await quoteCreated).json();

  await expect(page.getByRole("heading", { name: /quote for/i })).toBeVisible();
  expect(created.items[0].catalogue_surface_id).toBe(surfaceId);
  expect(created.items[0].material).toBe(materialName);
});

test("B_layout_and_extras_pickers_record_their_choice_on_the_itemised_result", async ({
  page,
}) => {
  const runId = uniqueRunId("remediation-b");
  await signUpAndLogIn(page, runId);

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  await page
    .getByLabel("Customer name")
    .fill(`Pytest Layout Customer ${runId}`);
  await page
    .getByLabel("Customer address", { exact: true })
    .fill("1 Synthetic Street, London");
  await page.getByLabel("Postcode", { exact: true }).fill("NW2 7RP");
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if ((await material.isVisible()) && !(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  await page.getByRole("button", { name: "Next: Layout", exact: true }).click();
  await page
    .getByLabel("Worktop layout", { exact: true })
    .selectOption("u_shape");
  await expect(
    page.getByRole("img", { name: /U-shape worktop plan, pieces A, B, C/ }),
  ).toBeVisible();
  await page.getByLabel("Length (mm)", { exact: true }).fill("2400");
  await page.getByLabel("Piece B length (mm)", { exact: true }).fill("1800");
  await page.getByLabel("Piece C length (mm)", { exact: true }).fill("1600");
  await page
    .getByRole("button", { name: "Next: Design details", exact: true })
    .click();
  await page.getByLabel("Sink / hob cutout", { exact: true }).check();
  await page
    .getByLabel("Sink mounting", { exact: true })
    .selectOption("Undermount");
  await page
    .getByRole("button", { name: "Next: Pricing", exact: true })
    .click();
  await setStoneJobPrice(page);
  await page.getByRole("button", { name: "Next: Review", exact: true }).click();
  const createdResponse = page.waitForResponse(
    (res) =>
      res.url().endsWith("/api/v1/quote") && res.request().method() === "POST",
  );
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if (!(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  if (
    await page
      .getByLabel("Your job price before discount and VAT (£)")
      .isVisible()
  ) {
    if (
      !(await page
        .getByLabel("Your job price before discount and VAT (£)")
        .inputValue())
    )
      await setStoneJobPrice(page);
  }
  await page.getByRole("button", { name: "Save Quote", exact: true }).click();
  const created = await (await createdResponse).json();
  expect(
    created.items.map((item: { length_mm: number }) => item.length_mm),
  ).toEqual([2400, 1800, 1600]);
  expect(created.slabs).toBeNull();
  expect(created.items[2].price_per_slab).toBeNull();
  // Assert on the itemised RESULT, not the form: the picker labels stay
  // on screen after calculating, so a bare getByText(/U-shape/) matched
  // the picker (passing without checking the result at all) or, once the
  // result rendered, two elements (a strict-mode failure). Wait for the
  // result heading, then match the exact notes line the quote records.
  await expect(
    page.getByRole("heading", {
      name: `Quote for Pytest Layout Customer ${runId}`,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Piece A. Layout: U-shape. Extras: Sink / hob cutout. Sink: Undermount",
      { exact: true },
    ),
  ).toBeVisible();
});

test("C_manual_job_price_records_edges_and_new_customer_drawing", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const runId = uniqueRunId("stone-recovery");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);
  const materialName = `Unlisted pilot marble ${runId}`;
  const customerName = `Pytest Drawing Customer ${runId}`;
  await page.goto("/quotes/new/stone");
  await page.getByLabel("Show all sections").check();
  await page.getByLabel("Customer name", { exact: true }).fill(customerName);
  await page
    .getByLabel("Customer address", { exact: true })
    .fill("1 Synthetic Street, London");
  await page.getByLabel("Postcode", { exact: true }).fill("NW2 7RP");
  await page.getByLabel("Material", { exact: true }).fill(materialName);
  await page.getByLabel("Length (mm)", { exact: true }).fill("2400");
  await page
    .getByLabel("Your job price before discount and VAT (£)")
    .fill("900");
  await page.getByLabel("Splashback included", { exact: true }).check();
  await expect(page.getByLabel("Splashback length (mm)")).toHaveCount(0);
  await page.getByLabel("Polished edge", { exact: true }).check();
  await page
    .getByLabel("Polished edge profile", { exact: true })
    .selectOption("Double ogee");
  await page.getByLabel("Upload layout drawing (optional)").setInputFiles({
    name: "pilot-plan.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(
      "%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF",
    ),
  });
  await expect(
    page.getByText(/(?:Ready to attach|Saved drawing): pilot-plan.pdf/),
  ).toBeVisible();
  const accepted = page.waitForResponse(
    (res) =>
      res.url().endsWith("/api/v1/quote") && res.request().method() === "POST",
  );
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if (!(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  if (
    await page
      .getByLabel("Your job price before discount and VAT (£)")
      .isVisible()
  ) {
    if (
      !(await page
        .getByLabel("Your job price before discount and VAT (£)")
        .inputValue())
    )
      await setStoneJobPrice(page);
  }
  await page.getByRole("button", { name: "Save Quote", exact: true }).click();
  const response = await accepted;
  expect(response.status()).toBe(200);
  const created = await response.json();
  expect(created.customer_id).toBeTruthy();
  expect(created.items[0].price_per_slab).toBeNull();
  expect(created.items[0].notes).toContain(
    "Polished edge profile: Double ogee",
  );
  expect(created.items[0].notes).toContain("pilot-plan.pdf");
  expect(created.total).toBe(900);
  await expect(
    page.getByRole("heading", { name: `Quote for ${customerName}` }),
  ).toBeVisible();
  const savedResponse = await api.get(`/api/v1/quotes/${created.id}`, {
    headers: authHeaders,
  });
  expect(savedResponse.status()).toBe(200);
  const savedQuote = await savedResponse.json();
  expect(savedQuote.items[0].notes).toContain("Double ogee");
  expect(savedQuote.site_address_line1).toBe("1 Synthetic Street, London");
  expect(savedQuote.site_postcode).toBe("NW2 7RP");
  const documents = await api.get(
    `/api/v1/documents?customer_id=${created.customer_id}`,
    { headers: authHeaders },
  );
  expect(documents.status()).toBe(200);
  const drawing = (await documents.json()).find(
    (doc: { original_filename: string }) =>
      doc.original_filename === "pilot-plan.pdf",
  );
  expect(drawing).toBeTruthy();
  const download = await api.get(`/api/v1/documents/${drawing.id}/download`, {
    headers: authHeaders,
  });
  expect(download.status()).toBe(200);
  expect(download.headers()["content-type"]).toContain("application/pdf");
  const invoice = await api.get(`/api/v1/quotes/${created.id}/invoice`, {
    headers: authHeaders,
  });
  expect(invoice.status()).toBe(200);
  expect(invoice.headers()["content-type"]).toContain("application/pdf");
});

test("D_expired_session_keeps_the_quote_draft_and_selected_file_without_anonymous_save", async ({
  page,
  context,
}) => {
  test.setTimeout(60_000);
  const runId = uniqueRunId("stone-expiry");
  const { api, authHeaders, ownerEmail, ownerPassword } = await signUpAndLogIn(
    page,
    runId,
  );
  await page.goto("/quotes/new/stone");
  await page.getByLabel("Show all sections").check();
  await page
    .getByLabel("Customer name", { exact: true })
    .fill(`Retained Pilot ${runId}`);
  await page
    .getByLabel("Customer address", { exact: true })
    .fill("1 Synthetic Street, London");
  await page.getByLabel("Postcode", { exact: true }).fill("NW2 7RP");
  await page.getByLabel("Length (mm)", { exact: true }).fill("2400");
  await page.getByLabel("Upload layout drawing (optional)").setInputFiles({
    name: "retained-plan.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%%EOF"),
  });
  await expect(
    page.getByText(/Ready to attach: retained-plan.pdf/),
  ).toBeVisible();
  await context.clearCookies();
  const denied = page.waitForResponse(
    (res) =>
      res.url().includes("/api/v1/catalogue/surfaces?") && res.status() === 401,
  );
  await page
    .getByRole("button", { name: "Browse materials", exact: true })
    .click();
  await denied;
  await expect(
    page
      .getByRole("link", { name: "Sign in in a new tab", exact: true })
      .first(),
  ).toBeVisible();
  await expect(page.getByLabel("Customer name", { exact: true })).toHaveValue(
    `Retained Pilot ${runId}`,
  );
  await expect(page.getByLabel("Length (mm)", { exact: true })).toHaveValue(
    "2400",
  );
  await expect(
    page.getByText(/Ready to attach: retained-plan.pdf/),
  ).toBeVisible();
  let quotePosts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/v1/quote"))
      quotePosts++;
  });
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if (!(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  if (
    await page
      .getByLabel("Your job price before discount and VAT (£)")
      .isVisible()
  ) {
    if (
      !(await page
        .getByLabel("Your job price before discount and VAT (£)")
        .inputValue())
    )
      await setStoneJobPrice(page);
  }
  await page.getByRole("button", { name: "Save Quote", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Sign in again" }),
  ).toContainText("Sign in again");
  expect(quotePosts).toBe(0);

  // The chooser clears its native value after selection so the same file can
  // be selected again. Prove the queued File survives by uploading it after
  // restoring the session, then compare the downloaded bytes.
  const signIn = await context.newPage();
  await signIn.goto("/login");
  await signIn.getByLabel("Email", { exact: true }).fill(ownerEmail);
  await signIn.getByLabel("Password", { exact: true }).fill(ownerPassword);
  await signIn.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(signIn).toHaveURL(/\/customers$/);
  await signIn.close();
  await page
    .getByRole("button", { name: "Check sign-in and retry", exact: true })
    .click();
  await expect(
    page.getByLabel("Link to existing customer (optional)"),
  ).toBeVisible();
  await expect(page.getByLabel("Customer name", { exact: true })).toHaveValue(
    `Retained Pilot ${runId}`,
  );
  await expect(
    page.getByText(/Ready to attach: retained-plan.pdf/),
  ).toBeVisible();
  await page
    .getByLabel("Your job price before discount and VAT (£)")
    .fill("900");
  const accepted = page.waitForResponse(
    (res) =>
      res.url().endsWith("/api/v1/quote") && res.request().method() === "POST",
  );
  for (const material of await page.locator('input[id$="-material"]').all()) {
    if (!(await material.inputValue()))
      await material.fill("Synthetic test stone");
  }
  if (
    await page
      .getByLabel("Your job price before discount and VAT (£)")
      .isVisible()
  ) {
    if (
      !(await page
        .getByLabel("Your job price before discount and VAT (£)")
        .inputValue())
    )
      await setStoneJobPrice(page);
  }
  await page.getByRole("button", { name: "Save Quote", exact: true }).click();
  const response = await accepted;
  expect(response.status()).toBe(200);
  const created = await response.json();
  const documents = await api.get(
    `/api/v1/documents?customer_id=${created.customer_id}`,
    { headers: authHeaders },
  );
  expect(documents.status()).toBe(200);
  const drawing = (await documents.json()).find(
    (doc: { original_filename: string }) =>
      doc.original_filename === "retained-plan.pdf",
  );
  expect(drawing).toBeTruthy();
  const download = await api.get(`/api/v1/documents/${drawing.id}/download`, {
    headers: authHeaders,
  });
  expect(download.status()).toBe(200);
  expect(await download.body()).toEqual(Buffer.from("%PDF-1.4\n%%EOF"));
  expect(quotePosts).toBe(1);
});
