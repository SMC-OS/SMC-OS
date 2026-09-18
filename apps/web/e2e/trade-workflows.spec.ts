import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

/**
 * GeoCore Premium OS Plan 01 (Sprint 040, Task 10) — the trade-adaptive
 * workflow engine's own E2E coverage, three journeys not already proven
 * by another spec:
 *
 *   1. An Electrical journey — a trade whose real stage sequence is
 *      nothing like Stone's (already proven end to end by
 *      full-system-journey.spec.ts), including Hold and Resume, driven
 *      entirely through the real Project 360 Workflow tab.
 *   2. A cross-trade Command Centre journey — an Electrical project and
 *      a Stone project both land on the SURVEY role despite completely
 *      different stage labels, proving the semantic-role aggregation
 *      Task 7/9 built is real, not just unit-tested.
 *   3. A legacy-safety journey — a project bound to the immutable
 *      legacy_v1 template (the only way any project could be bound to it
 *      is the Task 3 migration backfilling a pre-existing row; there is
 *      no way to create one through today's API/UI, so this spec seeds
 *      one directly via the same real-subprocess-against-the-real-
 *      database technique verify-helper.ts/billing-helper.ts already
 *      use) still renders correctly in Project 360, and the old
 *      PATCH /status endpoint - still the only way a pre-Plan-01
 *      integration would ever touch such a project - keeps the new
 *      `workflow` view in lockstep when the page reloads.
 */

function runPython(script: string): string {
  return execFileSync("python", ["-c", script.trim()], { cwd: REPO_ROOT, encoding: "utf-8" }).trim();
}

async function signUpVerifiedOwner(
  api: Awaited<ReturnType<typeof request.newContext>>,
  companyName: string,
  email: string,
  password: string
): Promise<{ token: string; headers: { Authorization: string } }> {
  const signup = await api.post("/api/v1/auth/signup", {
    data: { company_name: companyName, name: "Pytest E2E Owner", email, password },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(email);
  grantBillingAccess(email);
  const { access_token: token } = await signup.json();
  return { token, headers: { Authorization: `Bearer ${token}` } };
}

async function loginThroughUi(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);
}

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

test.describe("GeoCore Premium OS Plan 01 (Sprint 040) — trade-adaptive workflows", () => {
  test("an_electrical_project_moves_through_its_own_workflow_including_hold_and_resume", async ({
    page,
  }) => {
    const api = await request.newContext({ baseURL: BACKEND_URL });
    const email = `pytest-e2e-sprint040-electrical-${RUN_ID}@example.invalid`;
    const password = `Pytest-E2e-Sprint040-Electrical-Password-${RUN_ID}!`;
    const { headers } = await signUpVerifiedOwner(
      api,
      `Pytest E2E Sprint 040 Electrical Co ${RUN_ID}`,
      email,
      password
    );

    await loginThroughUi(page, email, password);

    // ---- Create an Electrical project through the real UI ----
    await page.goto("/projects/new");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Project name").fill(`Pytest E2E Sprint 040 Electrical Job ${RUN_ID}`);
    await page.getByLabel("Type of work").selectOption({ label: "Electrical" });
    await page.getByRole("button", { name: /save project|create project/i }).click();
    await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/, { timeout: 15_000 });
    const projectId = page.url().match(/\/projects\/([0-9a-f-]+)$/)![1];

    await page.getByRole("tab", { name: /workflow/i }).click();
    await expect(page.getByText("Enquiry", { exact: true }).first()).toBeVisible();

    // ---- Move forward through Electrical's own real sequence ----
    // (app/workflows/catalogue.py — nothing like Stone's Template/
    // Fabrication/QC/Installation vocabulary.)
    for (const stageLabel of ["Site Assessment", "Quote"]) {
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
    await expect(page.getByText("Quote", { exact: true }).first()).toBeVisible();

    // ---- Hold, then Resume back to where it was ----
    const holdResponse = page.waitForResponse(
      (res) =>
        res.url().endsWith(`/api/v1/projects/${projectId}/workflow/transition`) &&
        res.request().method() === "POST"
    );
    await page.getByRole("button", { name: /^hold$/i }).click();
    await holdResponse;
    await expect(page.getByText("On Hold", { exact: true }).first()).toBeVisible();

    const resumeButton = page.getByRole("button", { name: "Move to Quote" });
    await expect(resumeButton).toBeVisible();
    const resumeResponse = page.waitForResponse(
      (res) =>
        res.url().endsWith(`/api/v1/projects/${projectId}/workflow/transition`) &&
        res.request().method() === "POST"
    );
    await resumeButton.click();
    const resumed = await resumeResponse;
    expect((await resumed.json()).workflow.stage_key).toBe("quote");
    await expect(page.getByText("Quote", { exact: true }).first()).toBeVisible();

    // ---- Verify the full audit trail through the live API ----
    const historyRes = await api.get(`/api/v1/projects/${projectId}/workflow/history`, { headers });
    expect(historyRes.ok()).toBeTruthy();
    const history = await historyRes.json();
    expect(history.map((entry: { to_stage_key: string }) => entry.to_stage_key)).toEqual([
      "site_assessment",
      "quote",
      "on_hold",
      "quote",
    ]);

    await api.dispose();
  });

  test("the_command_centre_aggregates_different_trades_under_one_shared_role", async ({ page }) => {
    const api = await request.newContext({ baseURL: BACKEND_URL });
    const email = `pytest-e2e-sprint040-crosstrade-${RUN_ID}@example.invalid`;
    const password = `Pytest-E2e-Sprint040-Crosstrade-Password-${RUN_ID}!`;
    const { headers } = await signUpVerifiedOwner(
      api,
      `Pytest E2E Sprint 040 Cross-Trade Co ${RUN_ID}`,
      email,
      password
    );

    // ---- Create one Electrical and one Stone project through the real
    // API, and move each to its own trade's SURVEY-role stage ----
    const electricalRes = await api.post("/api/v1/projects", {
      headers,
      data: { name: `Pytest E2E Sprint 040 Cross-Trade Electrical ${RUN_ID}`, project_type: "electrical" },
    });
    expect(electricalRes.ok()).toBeTruthy();
    const electricalId = (await electricalRes.json()).id as string;
    const electricalMove = await api.post(`/api/v1/projects/${electricalId}/workflow/transition`, {
      headers,
      data: { target_stage_key: "site_assessment" },
    });
    expect(electricalMove.ok()).toBeTruthy();
    expect((await electricalMove.json()).workflow.role).toBe("survey");

    const stoneRes = await api.post("/api/v1/projects", {
      headers,
      data: { name: `Pytest E2E Sprint 040 Cross-Trade Stone ${RUN_ID}`, project_type: "stone" },
    });
    expect(stoneRes.ok()).toBeTruthy();
    const stoneId = (await stoneRes.json()).id as string;
    const stoneMove = await api.post(`/api/v1/projects/${stoneId}/workflow/transition`, {
      headers,
      data: { target_stage_key: "measure_site_visit" },
    });
    expect(stoneMove.ok()).toBeTruthy();
    expect((await stoneMove.json()).workflow.role).toBe("survey");

    // ---- The Command Centre, through the real browser, counts both
    // under the one shared "Survey" role ----
    await loginThroughUi(page, email, password);
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("Business Command Centre")).toBeVisible();

    const surveyRow = page.getByText("Survey", { exact: true }).locator("xpath=..");
    await expect(surveyRow).toContainText("2");

    await api.dispose();
  });

  test("a_legacy_bound_project_renders_correctly_and_the_old_status_endpoint_keeps_it_in_sync", async ({
    page,
  }) => {
    const api = await request.newContext({ baseURL: BACKEND_URL });
    const email = `pytest-e2e-sprint040-legacy-${RUN_ID}@example.invalid`;
    const password = `Pytest-E2e-Sprint040-Legacy-Password-${RUN_ID}!`;
    const { headers } = await signUpVerifiedOwner(
      api,
      `Pytest E2E Sprint 040 Legacy Co ${RUN_ID}`,
      email,
      password
    );
    const projectName = `Pytest E2E Sprint 040 Legacy Job ${RUN_ID}`;

    // ---- Seed a legacy_v1-bound project directly — the only way any
    // project is ever bound to legacy_v1 is Task 3's migration
    // backfilling a row that predates this plan; there is no API/UI path
    // that produces one today, by design (Task 4 always binds a new
    // project to a real trade workflow). ----
    const projectId = runPython(`
import uuid
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import Project

db = SessionLocal()
user = crud.get_user_by_email(db, ${JSON.stringify(email)})
template = crud.get_system_workflow_template_by_key(db, "legacy_v1")
stage = crud.get_workflow_stage_by_key(db, template.id, "booked")
project = Project(
    id=uuid.uuid4(), tenant_id=user.tenant_id, name=${JSON.stringify(projectName)},
    status="booked", workflow_template_id=template.id, workflow_stage_id=stage.id,
)
db.add(project)
db.commit()
print(project.id)
db.close()
`);

    await loginThroughUi(page, email, password);
    await page.goto(`/projects/${projectId}`);
    await page.waitForLoadState("networkidle");
    // The header shows the legacy project's real workflow view — Booked,
    // mapped straight off legacy_v1's own stage of that same key — never
    // a guessed or reinterpreted value.
    await expect(page.getByText("Booked", { exact: true }).first()).toBeVisible();

    // ---- A pre-Plan-01 integration still calling PATCH /status (the
    // only path Project 360 itself no longer exposes in its own UI) must
    // still move this project's workflow view in lockstep (Task 5) ----
    const statusRes = await api.patch(`/api/v1/projects/${projectId}/status`, {
      headers,
      data: { status: "templated" },
    });
    expect(statusRes.ok()).toBeTruthy();
    const updated = await statusRes.json();
    expect(updated.status).toBe("templated");
    expect(updated.workflow.template_key).toBe("legacy_v1");
    expect(updated.workflow.stage_key).toBe("templated");

    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("Templated", { exact: true }).first()).toBeVisible();

    await api.dispose();
  });
});
