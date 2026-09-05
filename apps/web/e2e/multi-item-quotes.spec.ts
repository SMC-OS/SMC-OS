import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 033 (Workstream C) — true multi-line-item quotes, through the
 * real browser against the real Next.js app and real FastAPI server (see
 * playwright.config.ts's webServer). Quote approval/project handoff
 * continuity for the new architecture is proven by the pre-existing
 * e2e/quote-handoff.spec.ts (same approve/handoff code paths, item-list-
 * agnostic) — this spec covers what's new: the multi-item editor itself
 * and AI-generated multi-item drafts.
 *
 * The AI draft scenario mocks the backend's /quotes/ai-draft response via
 * page.route() — no OPENAI_API_KEY exists in this (or any CI) environment
 * (see docs/SPRINTS/sprint-032.md/sprint-033.md), so this proves the
 * *frontend's* multi-item draft handling for real, against a
 * realistically-shaped response, without needing a live OpenAI call.
 */

// Each test gets its own unique identity (not one shared across the whole
// file) — three independent tests each calling /auth/signup with the same
// email would conflict (409) on the second and third calls.
function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: import("@playwright/test").Page, runId: string) {
  const companyName = `Pytest E2E Sprint 033 Co ${runId}`;
  const ownerEmail = `pytest-e2e-sprint033-${runId}@example.invalid`;
  const ownerPassword = `pytest-e2e-sprint033-password-${runId}`;

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
  await api.dispose();

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);
}

test("a_three_item_quote_can_be_created_manually_and_remains_accessible", async ({ page }) => {
  const runId = uniqueRunId("three-item");
  await signUpAndLogIn(page, runId);

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  await page.getByLabel("Customer name").fill(`Pytest Multi-Item Customer ${runId}`);

  // Item 1 (worktop, defaults) — just needs a length.
  await page.getByLabel("Length (mm)").first().fill("2400");

  // Item 2 — duplicate item 1, then edit its type/length so it's
  // independent, proving duplication doesn't leave two rows permanently
  // tied together.
  await page.getByRole("button", { name: "Duplicate" }).first().click();
  await expect(page.getByText("Item 2", { exact: true })).toBeVisible();
  const item2Type = page.locator("[id$='-type']").nth(1);
  await item2Type.selectOption("island");
  await page.locator("[id$='-length']").nth(1).fill("2200");
  await page.locator("[id$='-width']").nth(1).fill("1000");

  // Item 3 — a fresh added row, independently dimensioned.
  await page.getByRole("button", { name: "+ Add item" }).click();
  await expect(page.getByText("Item 3", { exact: true })).toBeVisible();
  const item3Type = page.locator("[id$='-type']").nth(2);
  await item3Type.selectOption("splashback");
  await page.locator("[id$='-length']").nth(2).fill("1200");
  await page.locator("[id$='-width']").nth(2).fill("150");

  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const quoteResponse = await quoteCreated;
  expect(quoteResponse.status()).toBe(200);
  const body = await quoteResponse.json();
  expect(body.items).toHaveLength(3);

  // Each item kept its own independent length — none inherited another's.
  const lengths = body.items.map((item: { length_mm: number }) => item.length_mm).sort();
  expect(lengths).toEqual([1200, 2200, 2400]);

  await expect(page.getByText(/quote for pytest multi-item customer/i)).toBeVisible();

  // ---- Existing quote remains accessible after navigating away ----
  const quoteId = body.id as string;
  await page.goto("/quotes");
  await page.waitForLoadState("networkidle");
  await page.goto(`/quotes/${quoteId}`);
  await page.waitForLoadState("networkidle");
  // Sprint 036 relabelled the detail page's item section from "3 items"
  // to "3 lines" (a quote now has lines, which may be slabs or general
  // construction work). The property under test is unchanged: all three
  // independently-dimensioned items survive the round trip and are
  // rendered, each with its own length.
  await expect(page.getByText(/3 lines/i)).toBeVisible();
  await expect(page.getByText(/2400mm/)).toBeVisible();
  await expect(page.getByText(/2200mm/)).toBeVisible();
  await expect(page.getByText(/1200mm/)).toBeVisible();
});

test("removing an item leaves the others intact and never removes the last row", async ({ page }) => {
  await signUpAndLogIn(page, uniqueRunId("remove-item"));

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  await expect(page.getByRole("button", { name: "Remove" })).toBeDisabled();

  await page.getByRole("button", { name: "+ Add item" }).click();
  await expect(page.getByText("Item 2", { exact: true })).toBeVisible();

  const removeButtons = page.getByRole("button", { name: "Remove" });
  await expect(removeButtons.first()).toBeEnabled();
  await removeButtons.first().click();

  await expect(page.getByText("Item 2", { exact: true })).not.toBeVisible();
  await expect(page.getByText("Item 1", { exact: true })).toBeVisible();
});

test("a_multi_item_quote_can_be_generated_through_simo_ai", async ({ page }) => {
  const runId = uniqueRunId("ai-multi-item");
  await signUpAndLogIn(page, runId);

  await page.route("**/api/v1/quotes/ai-draft", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        customer: `Pytest AI Multi-Item Customer ${runId}`,
        postcode: null,
        items: [
          {
            item_type: "worktop",
            material: "Calacatta Oro",
            material_raw: null,
            material_match_status: "found",
            material_candidates: [],
            thickness: "20mm",
            quantity: 1,
            length_mm: 2400,
            width_mm: 600,
            thickness_mm: 20,
            unit_input: "mm",
            warnings: [],
          },
          {
            item_type: "island",
            material: "Calacatta Oro",
            material_raw: null,
            material_match_status: "found",
            material_candidates: [],
            thickness: "20mm",
            quantity: 1,
            length_mm: 2200,
            width_mm: 1000,
            thickness_mm: 20,
            unit_input: "mm",
            warnings: [],
          },
          {
            item_type: "splashback",
            material: "Calacatta Oro",
            material_raw: null,
            material_match_status: "found",
            material_candidates: [],
            thickness: "20mm",
            quantity: 2,
            length_mm: 1200,
            width_mm: 600,
            thickness_mm: 20,
            unit_input: "mm",
            warnings: [],
          },
        ],
        warnings: [],
      }),
    });
  });

  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");

  await page
    .getByPlaceholder(/calacatta oro 20mm/i)
    .fill(
      "Create a quote using Calacatta Oro 20mm for a 2400 x 600 worktop, a 2200 x 1000 island and two 1200 x 600 splashbacks."
    );
  await page.getByRole("button", { name: "Generate Draft" }).click();

  await expect(page.getByText("Interpreted 3 items")).toBeVisible();
  await page.getByRole("button", { name: "Use these items" }).click();

  await expect(page.getByText("Item 3", { exact: true })).toBeVisible();
  await expect(page.locator("[id$='-length']").nth(0)).toHaveValue("2400");
  await expect(page.locator("[id$='-length']").nth(1)).toHaveValue("2200");
  await expect(page.locator("[id$='-length']").nth(2)).toHaveValue("1200");

  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const quoteResponse = await quoteCreated;
  expect(quoteResponse.status()).toBe(200);
  const body = await quoteResponse.json();
  expect(body.items).toHaveLength(3);
  expect(body.items.find((i: { item_type: string }) => i.item_type === "splashback").quantity).toBe(2);
});
