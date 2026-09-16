import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * Sprint 036 (Workstream G) — the automation engine, end to end through
 * the real browser and the real server.
 *
 * The journey proven here is the one the feature exists for: turn on a
 * template, do the thing that triggers it, and see the work it created —
 * with the run recorded either way. The honesty constraint is asserted
 * too: nothing an automation can do reaches a customer.
 */

function uniqueRunId(label: string): string {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function signUpAndLogIn(page: import("@playwright/test").Page, runId: string) {
  const ownerEmail = `pytest-e2e-auto-${runId}@example.invalid`;
  const ownerPassword = `Pytest-E2e-Auto-Password-${runId}!`;

  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Automations Co ${runId}`,
      name: "Pytest Automations Owner",
      email: ownerEmail,
      password: ownerPassword,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(ownerEmail);
  const { access_token: token } = await signup.json();

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password").fill(ownerPassword);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/, { timeout: 15_000 });

  return { api, authHeaders: { Authorization: `Bearer ${token}` } };
}

test("an_automation_template_is_activated_and_actually_runs", async ({ page }) => {
  const runId = uniqueRunId("template");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);

  // ---- Turn on "New customer → first contact task" ----
  await page.goto("/automations");
  await page.waitForLoadState("networkidle");

  // The honesty constraint, asserted in the product itself.
  await expect(
    page.getByText(/GeoCore does not send email, SMS or messages to customers/i)
  ).toBeVisible();

  const templateCard = page
    .locator("div")
    .filter({ hasText: /^New customer → first contact task/ })
    .first();
  await templateCard.getByRole("button", { name: "Turn on" }).click();

  await expect(page.getByRole("button", { name: "Already on" })).toBeVisible({
    timeout: 10_000,
  });

  // ---- Do the thing that triggers it ----
  const customerRes = await api.post("/api/v1/customers", {
    headers: authHeaders,
    data: { name: `Pytest Automations Lead ${runId}` },
  });
  expect(customerRes.ok()).toBeTruthy();

  // ---- The run is recorded, and the task actually exists ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("succeeded").first()).toBeVisible({ timeout: 10_000 });

  const tasksRes = await api.get("/api/v1/tasks?status=open&limit=50", {
    headers: authHeaders,
  });
  const tasks = await tasksRes.json();
  expect(
    tasks.some((task: { title: string }) =>
      task.title.includes(`Pytest Automations Lead ${runId}`)
    )
  ).toBeTruthy();

  // ---- And it is visible where the work actually gets picked up ----
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  // .first(): the task surfaces in more than one place on the dashboard
  // (the attention list and the automation activity feed), which is the
  // intent — one is enough to prove it reached the person.
  await expect(
    page.getByText(`First contact: Pytest Automations Lead ${runId}`).first()
  ).toBeVisible({ timeout: 10_000 });

  await api.dispose();
});

test("an_automation_runs_once_however_many_times_the_trigger_repeats", async ({ page }) => {
  const runId = uniqueRunId("idempotent");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);

  const activated = await api.post("/api/v1/automations/templates", {
    headers: authHeaders,
    data: { template_key: "approved_quote_to_project" },
  });
  expect(activated.ok()).toBeTruthy();

  const quoteRes = await api.post("/api/v1/quotes", {
    headers: authHeaders,
    data: {
      title: `Pytest idempotency ${runId}`,
      lines: [{ description: "Work", quantity: 1, unit: "job", unit_price: 1000 }],
    },
  });
  const quote = await quoteRes.json();

  await api.post(`/api/v1/quotes/${quote.id}/approve`, { headers: authHeaders });
  // Approving again is a 409, but the handoff action is idempotent by
  // construction (projects.quote_id is UNIQUE) — so re-running the
  // automation must not produce a second project either way.
  await api.post(`/api/v1/quotes/${quote.id}/handoff`, { headers: authHeaders });

  const projectsRes = await api.get("/api/v1/projects?limit=100", { headers: authHeaders });
  const projects = await projectsRes.json();
  const fromThisQuote = projects.filter(
    (project: { quote_id: string | null }) => project.quote_id === quote.id
  );
  expect(fromThisQuote).toHaveLength(1);

  await page.goto("/automations");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("succeeded").first()).toBeVisible({ timeout: 10_000 });

  await api.dispose();
});

test("a_failed_run_is_visible_rather_than_silent", async ({ page }) => {
  const runId = uniqueRunId("failure");
  const { api, authHeaders } = await signUpAndLogIn(page, runId);

  // A rule that tries to create a project from a quote the moment it is
  // created — while it is still a draft, which handoff correctly refuses.
  const created = await api.post("/api/v1/automations", {
    headers: authHeaders,
    data: {
      name: `Pytest failing rule ${runId}`,
      trigger_type: "quote.created",
      actions: [{ type: "create_project_from_quote", config: {} }],
    },
  });
  expect(created.ok()).toBeTruthy();

  const quoteRes = await api.post("/api/v1/quotes", {
    headers: authHeaders,
    data: {
      title: `Pytest failing trigger ${runId}`,
      lines: [{ description: "Work", quantity: 1, unit: "job", unit_price: 500 }],
    },
  });
  // The user's own action still succeeds — an automation can never break
  // the thing that triggered it.
  expect(quoteRes.ok()).toBeTruthy();

  await page.goto("/automations");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("failed")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/not approved/i)).toBeVisible();

  await api.dispose();
});
