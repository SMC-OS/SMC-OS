import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

// Sprint 039 Production Readiness Defect Gate, Blocker 1 — inviting a
// teammate now requires a verified email (require_verified_email on
// app/invitations/router.py's create_invitation). A fresh signup is
// unverified by design (see app/auth/service.py's signup()), so this
// setup step mints and confirms a real token the same way
// EmailVerificationService.send_verification_email() does — see
// e2e/email-verification.spec.ts's identical helper for the full
// rationale — rather than mocking or bypassing the check this spec
// isn't testing.
async function verifyOwnerEmail(api: import("@playwright/test").APIRequestContext, email: string) {
  const script = `
import hashlib, secrets, uuid
from datetime import datetime, timedelta, timezone
from app.database import crud
from app.database.database import SessionLocal

db = SessionLocal()
user = crud.get_user_by_email(db, ${JSON.stringify(email)})
raw_token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
crud.create_email_verification_token(
    db, id=uuid.uuid4(), user_id=user.id, token_hash=token_hash,
    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
)
db.close()
print(raw_token)
`.trim();
  const rawToken = execFileSync("python", ["-c", script], { cwd: REPO_ROOT, encoding: "utf-8" })
    .trim()
    .split("\n")
    .pop() as string;
  const confirm = await api.post("/api/v1/auth/email/verify/confirm", {
    data: { token: rawToken },
  });
  expect(confirm.ok()).toBeTruthy();
}

/**
 * Sprint 023 — true browser E2E for project operations (staff assignment +
 * validated status transitions). Structural twin of
 * e2e/site-visit-scheduling.spec.ts (Sprint 022). Setup (tenant, Owner,
 * Staff via a real invitation accept, and a booked Project) goes through
 * the real API directly, but the critical business actions — assigning
 * Staff and advancing the Project's status — run through the real
 * Chromium browser against the real Next.js app and real FastAPI server
 * (see playwright.config.ts's webServer). Nothing here mocks fetch, the
 * router, or the API client; page.waitForResponse below only observes the
 * real network response, it never intercepts or fulfills it.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 023 Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint023-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `Pytest-E2e-Sprint023-Password-${RUN_ID}!`;
const STAFF_EMAIL = `pytest-e2e-sprint023-staff-${RUN_ID}@example.invalid`;
const STAFF_NAME = `Pytest E2E Staff ${RUN_ID}`;
const STAFF_PASSWORD = `Pytest-E2e-Sprint023-Staff-Password-${RUN_ID}!`;
const PROJECT_NAME = `Pytest E2E Sprint 023 Project ${RUN_ID}`;

test("a_project_can_be_assigned_and_advanced_through_the_ui_and_persists", async ({ page }) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Setup through the real API (not TestClient, not mocked) ----
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: COMPANY_NAME,
      name: "Pytest E2E Owner",
      email: OWNER_EMAIL,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(OWNER_EMAIL);
  grantBillingAccess(OWNER_EMAIL);
  const { access_token: ownerToken } = await signup.json();
  const ownerHeaders = { Authorization: `Bearer ${ownerToken}` };
  await verifyOwnerEmail(api, OWNER_EMAIL);

  // Real Staff user via a real invitation accept — same mechanism the
  // product actually uses to create Staff accounts (Sprint 011), not a
  // direct DB insert.
  const invitation = await api.post("/api/v1/invitations", {
    headers: ownerHeaders,
    data: { email: STAFF_EMAIL },
  });
  expect(invitation.ok()).toBeTruthy();
  const { token: invitationToken } = await invitation.json();

  const accepted = await api.post(`/api/v1/invitations/token/${invitationToken}/accept`, {
    data: { name: STAFF_NAME, password: STAFF_PASSWORD },
  });
  expect(accepted.ok()).toBeTruthy();

  const projectRes = await api.post("/api/v1/projects", {
    headers: ownerHeaders,
    data: { name: PROJECT_NAME },
  });
  expect(projectRes.ok()).toBeTruthy();
  const projectId = (await projectRes.json()).id as string;

  // ---- Authenticate through the real login UI ----
  // networkidle after each full navigation: Next dev/Turbopack compiles a
  // route on first visit, and a Playwright click can otherwise land before
  // React attaches the form's onSubmit handler, causing a native (non-JS)
  // form submission instead of the real login request.
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // ---- Open the real Project detail page: Team tab (GeoCore Premium OS
  // Plan 01, Sprint 040, Task 8 — assignment lives on its own tab now) ----
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /^team$/i }).click();
  const assignSelect = page.getByLabel("Assigned to");
  await expect(assignSelect).toBeVisible();
  await expect(page.getByRole("option", { name: STAFF_NAME })).toBeAttached();

  // ---- Assign through the UI (not a direct API call) ----
  const assignResponsePromise = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/projects/${projectId}/assign`) &&
      res.request().method() === "PATCH"
  );
  await assignSelect.selectOption({ label: STAFF_NAME });
  const assignResponse = await assignResponsePromise;
  expect(assignResponse.status()).toBe(200);
  const assignedProject = await assignResponse.json();
  expect(assignedProject.assigned_user_id).toBeTruthy();

  // ---- Verify persistence: reload proves it was saved, not just client state ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.getByRole("tab", { name: /^team$/i }).click();
  await expect(page.getByLabel("Assigned to")).toHaveValue(assignedProject.assigned_user_id);

  // ---- Move the Project through its real trade workflow, through the
  // Workflow tab (Task 8) — this Project has no project_type, so it's
  // bound to the general_v1 fallback (Task 4): enquiry -> site_visit is
  // its first real forward move. ----
  await page.getByRole("tab", { name: /workflow/i }).click();
  const moveButton = page.getByRole("button", { name: "Move to Site Visit" });
  await expect(moveButton).toBeVisible();
  const transitionResponsePromise = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/projects/${projectId}/workflow/transition`) &&
      res.request().method() === "POST"
  );
  await moveButton.click();
  const transitionResponse = await transitionResponsePromise;
  expect(transitionResponse.status()).toBe(200);
  const movedProject = await transitionResponse.json();
  expect(movedProject.workflow.stage_key).toBe("site_visit");
  expect(movedProject.workflow.role).toBe("survey");

  await expect(page.getByRole("button", { name: "Move to Quote" })).toBeVisible();

  // ---- Verify persistence again after reload ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Survey", { exact: true }).first()).toBeVisible();

  // ---- Verify persisted state through the live API (server-side truth) ----
  const persistedProjectRes = await api.get(`/api/v1/projects/${projectId}`, {
    headers: ownerHeaders,
  });
  expect(persistedProjectRes.ok()).toBeTruthy();
  const persistedProject = await persistedProjectRes.json();
  expect(persistedProject.assigned_user_id).toBe(assignedProject.assigned_user_id);
  expect(persistedProject.workflow.stage_key).toBe("site_visit");

  // ---- Verify the workflow transition's own audit trail (Task 5) ----
  const historyRes = await api.get(`/api/v1/projects/${projectId}/workflow/history`, {
    headers: ownerHeaders,
  });
  expect(historyRes.ok()).toBeTruthy();
  const history = await historyRes.json();
  expect(history).toHaveLength(1);
  expect(history[0].from_stage_key).toBe("enquiry");
  expect(history[0].to_stage_key).toBe("site_visit");

  // ---- Verify exactly one project_assigned activity exists for this
  // Project (tenant-scoped: GET /activity is always the caller's own
  // tenant — see app/activity/router.py). The workflow move above has its
  // own dedicated audit trail (ProjectWorkflowHistory, verified above) —
  // it does not also write a project_status_changed ActivityLog entry. ----
  const assignedActivityRes = await api.get(
    "/api/v1/activity?limit=50&type=project_assigned",
    { headers: ownerHeaders }
  );
  expect(assignedActivityRes.ok()).toBeTruthy();
  const assignedActivity = await assignedActivityRes.json();
  const matchingAssigned = assignedActivity.filter((event: { description: string | null }) =>
    (event.description ?? "").includes(projectId)
  );
  expect(matchingAssigned).toHaveLength(1);

  await api.dispose();
});
