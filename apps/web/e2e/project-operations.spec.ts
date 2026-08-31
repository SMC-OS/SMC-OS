import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

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
const OWNER_PASSWORD = `pytest-e2e-sprint023-password-${RUN_ID}`;
const STAFF_EMAIL = `pytest-e2e-sprint023-staff-${RUN_ID}@example.invalid`;
const STAFF_NAME = `Pytest E2E Staff ${RUN_ID}`;
const STAFF_PASSWORD = `pytest-e2e-sprint023-staff-password-${RUN_ID}`;
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
  const { access_token: ownerToken } = await signup.json();
  const ownerHeaders = { Authorization: `Bearer ${ownerToken}` };

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

  const quoted = await api.patch(`/api/v1/projects/${projectId}/status`, {
    headers: ownerHeaders,
    data: { status: "quoted" },
  });
  expect(quoted.ok()).toBeTruthy();
  const booked = await api.patch(`/api/v1/projects/${projectId}/status`, {
    headers: ownerHeaders,
    data: { status: "booked" },
  });
  expect(booked.ok()).toBeTruthy();
  expect((await booked.json()).status).toBe("booked");

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

  // ---- Open the real Project detail page ----
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Project Operations", { exact: true })).toBeVisible();
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
  await expect(page.getByLabel("Assigned to")).toHaveValue(assignedProject.assigned_user_id);

  // ---- Advance the Project's status through the UI ----
  const advanceButton = page.getByRole("button", { name: "Advance to Templated" });
  await expect(advanceButton).toBeVisible();
  const statusResponsePromise = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/projects/${projectId}/status`) &&
      res.request().method() === "PATCH"
  );
  await advanceButton.click();
  const statusResponse = await statusResponsePromise;
  expect(statusResponse.status()).toBe(200);
  expect((await statusResponse.json()).status).toBe("templated");

  await expect(page.getByText("Templated", { exact: true })).toBeVisible();

  // ---- Verify persistence again after reload ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Templated", { exact: true })).toBeVisible();

  // ---- Verify persisted state through the live API (server-side truth) ----
  const persistedProjectRes = await api.get(`/api/v1/projects/${projectId}`, {
    headers: ownerHeaders,
  });
  expect(persistedProjectRes.ok()).toBeTruthy();
  const persistedProject = await persistedProjectRes.json();
  expect(persistedProject.assigned_user_id).toBe(assignedProject.assigned_user_id);
  expect(persistedProject.status).toBe("templated");

  // ---- Verify exactly one project_assigned and one
  // project_status_changed activity exist for this Project (tenant-scoped:
  // GET /activity is always the caller's own tenant — see
  // app/activity/router.py) ----
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

  // Setup above already made two status transitions of its own
  // (enquiry -> quoted -> booked) through the real API, so this checks for
  // exactly the one transition the UI action just caused (booked ->
  // templated), not every project_status_changed event for this Project.
  const statusChangedActivityRes = await api.get(
    "/api/v1/activity?limit=50&type=project_status_changed",
    { headers: ownerHeaders }
  );
  expect(statusChangedActivityRes.ok()).toBeTruthy();
  const statusChangedActivity = await statusChangedActivityRes.json();
  const matchingStatusChanged = statusChangedActivity.filter(
    (event: { description: string | null }) =>
      event.description === `Project ${projectId} moved from booked to templated`
  );
  expect(matchingStatusChanged).toHaveLength(1);

  await api.dispose();
});
