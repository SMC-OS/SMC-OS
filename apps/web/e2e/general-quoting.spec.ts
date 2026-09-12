import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 036 (Workstream E) — universal quoting, through the real
 * browser against the real Next.js app and real FastAPI server.
 *
 * This is the sprint's central product claim and it is asserted end to
 * end: a bathroom refit is priced line by line, sent, approved and turned
 * into a project, with no slab, no material catalogue and no stone
 * anywhere in the flow — while the specialist stone template is still
 * reachable and still works (covered by e2e/multi-item-quotes.spec.ts).
 */

// Each test signs up its own identity rather than sharing one across the
// file — three tests calling /auth/signup with the same email would
// conflict (409) on the second and third, exactly as
// e2e/multi-item-quotes.spec.ts documents.
function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: import("@playwright/test").Page, runId: string) {
  const ownerEmail = `pytest-e2e-036-${runId}@example.invalid`;
  const ownerPassword = `pytest-e2e-036-password-${runId}`;
  const customerName = `Pytest E2E 036 Customer ${runId}`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 036 Co ${runId}`,
      name: "Pytest E2E 036 Owner",
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(signup.ok()).toBeTruthy();
  const { access_token: token } = await signup.json();
  const authHeaders = { Authorization: `Bearer ${token}` };

  const customerRes = await api.post("/api/v1/customers", {
    headers: authHeaders,
    data: {
      name: customerName,
      customer_type: "company",
      company_name: `${customerName} Ltd`,
      address_line1: "14 Elm Road",
      city: "Manchester",
      postcode: "M1 4BT",
    },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customer = await customerRes.json();

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });

  return { api, authHeaders, customer, customerName, ownerEmail, ownerPassword };
}

test("a_general_construction_quote_is_priced_sent_approved_and_becomes_a_project", async ({
  page,
}) => {
  const { api, authHeaders, customer } = await signUpAndLogIn(page, uniqueRunId("general"));

  // ---- Price a bathroom refit through the general builder ----
  await page.goto("/quotes/new");
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Quote title").fill("Bathroom refit, 14 Elm Road");
  await page.getByLabel("Customer").selectOption(customer.id);
  await page.getByLabel("Type of work").selectOption("bathroom");

  // The site address comes across from the customer rather than being
  // retyped.
  await expect(page.getByLabel("Address line 1")).toHaveValue("14 Elm Road");
  await expect(page.getByLabel("Town or city")).toHaveValue("Manchester");

  await page
    .getByLabel("Scope of works")
    .fill("Strip out, first and second fix, tile, fit new suite, make good.");

  await page.getByLabel("Description").fill("Strip out existing bathroom");
  await page.getByLabel("Quantity").fill("2.5");
  await page.getByLabel("Unit").selectOption("day");
  await page.getByLabel("Rate (£)").fill("320");

  await page.getByRole("button", { name: /add line/i }).click();
  await page.getByLabel("Description").nth(1).fill("Sanitaryware and brassware");
  await page.getByLabel("Quantity").nth(1).fill("1");
  await page.getByLabel("Rate (£)").nth(1).fill("1450.50");

  await page.getByLabel("Exclusions").fill("Making good to decoration.");

  // 2.5 x 320 = 800.00, plus 1450.50 = 2250.50; +20% VAT = 2700.60.
  await expect(page.getByText("£2,700.60").first()).toBeVisible();

  const quoteCreated = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/quotes") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /create quote/i }).click();
  const created = await (await quoteCreated).json();

  // ---- The persisted quote is a general quote with no slab data ----
  expect(created.quote_kind).toBe("general");
  expect(created.total).toBe(2700.6);
  expect(created.material).toBeNull();
  expect(created.length_mm).toBeNull();
  expect(created.items).toHaveLength(2);
  expect(created.items[0].line_kind).toBe("labour");
  expect(created.items[0].quantity).toBe(2.5);

  await page.getByRole("link", { name: /open the quote/i }).click();
  await page.waitForURL(/\/quotes\/[0-9a-f-]+$/);

  // ---- Mark as sent, then approve, then create the project ----
  await page.getByRole("button", { name: "Mark as sent" }).click();
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Create the project" }).click();
  await page.waitForURL(/\/projects\/[0-9a-f-]+$/, { timeout: 15_000 });

  // ---- The project carries what the quote already knew ----
  const projectId = page.url().split("/projects/")[1];
  const projectRes = await api.get(`/api/v1/projects/${projectId}`, {
    headers: authHeaders,
  });
  expect(projectRes.ok()).toBeTruthy();
  const project = await projectRes.json();
  expect(project.project_type).toBe("bathroom");
  expect(project.site_city).toBe("Manchester");
  expect(project.estimated_value).toBe(2700.6);

  await api.dispose();
});

test("the_stone_template_is_still_offered_and_still_reachable", async ({ page }) => {
  const { api } = await signUpAndLogIn(page, uniqueRunId("stone-template"));

  await page.goto("/quotes/new");
  await page.waitForLoadState("networkidle");

  // Offered from the general builder, not hidden — it is the better tool
  // for that job.
  await page.getByText("Quoting stone or worktops?").click();
  await page.waitForURL(/\/quotes\/new\/stone$/);
  await expect(
    page.getByRole("heading", { name: /stone & worktop quote/i })
  ).toBeVisible();
  // The slab calculator's own inputs, unchanged.
  await expect(page.getByLabel("Material").first()).toBeVisible();

  await api.dispose();
});

test("both_kinds_of_quote_appear_in_one_list", async ({ page }) => {
  const runId = uniqueRunId("mixed-list");
  const { api, authHeaders, customer, customerName } = await signUpAndLogIn(page, runId);

  await api.post("/api/v1/quotes", {
    headers: authHeaders,
    data: {
      title: `Re-roof ${runId}`,
      trade: "roofing",
      customer_id: customer.id,
      lines: [{ description: "Re-roof", quantity: 1, unit: "job", unit_price: 6000 }],
    },
  });
  await api.post("/api/v1/quote", {
    headers: authHeaders,
    data: {
      customer: customerName,
      customer_id: customer.id,
      material: "Calacatta Gold",
      thickness: "20mm",
      kitchen_length: 3,
      postcode: "E2E-036",
    },
  });

  await page.goto("/quotes");
  await page.waitForLoadState("networkidle");

  await expect(page.getByText(`Re-roof ${runId}`)).toBeVisible();
  await expect(page.getByText(/Calacatta Gold/)).toBeVisible();

  await api.dispose();
});

// Sprint 039 Production Readiness Defect Gate, Blocker 5 — the backend's
// PATCH /quotes/{id} and the frontend's updateGeneralQuote API client both
// already existed and were already fully tested; nothing in the UI ever
// called either. This proves the missing entry point end to end, and that
// it disappears exactly where the backend would refuse it anyway.
test("a_draft_general_quote_can_be_edited_and_the_change_is_saved", async ({ page }) => {
  const runId = uniqueRunId("edit");
  const { api, authHeaders, customer } = await signUpAndLogIn(page, runId);

  const created = await (
    await api.post("/api/v1/quotes", {
      headers: authHeaders,
      data: {
        title: `Kitchen refit ${runId}`,
        trade: "kitchen",
        customer_id: customer.id,
        lines: [
          { description: "Strip out existing kitchen", quantity: 2, unit: "day", unit_price: 300 },
        ],
      },
    })
  ).json();
  expect(created.total).toBe(720); // 2 x 300 = 600, +20% VAT = 720.

  await page.goto(`/quotes/${created.id}`);
  await page.waitForLoadState("networkidle");

  await page.getByRole("link", { name: "Edit" }).click();
  await page.waitForURL(`**/quotes/${created.id}/edit`);

  // The existing line is pre-filled, not started from a blank form.
  await expect(page.getByLabel("Description")).toHaveValue("Strip out existing kitchen");
  await expect(page.getByLabel("Quantity")).toHaveValue(2);

  await page.getByLabel("Quantity").fill("3");

  const quoteUpdated = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/quotes/${created.id}`) &&
      response.request().method() === "PATCH"
  );
  await page.getByRole("button", { name: /save changes/i }).click();
  const updated = await (await quoteUpdated).json();

  // 3 x 300 = 900, +20% VAT = 1080 — the server re-priced it, not the form.
  expect(updated.total).toBe(1080);

  await page.getByRole("link", { name: /back to the quote/i }).click();
  await page.waitForURL(`**/quotes/${created.id}`);
  await expect(page.getByText("£1,080.00")).toBeVisible();

  // Once sent, the same quote is a document the customer already has —
  // editing it is no longer offered.
  await page.getByRole("button", { name: "Mark as sent" }).click();
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Edit" })).not.toBeVisible();

  await api.dispose();
});
