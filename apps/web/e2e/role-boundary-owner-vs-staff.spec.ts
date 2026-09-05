import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.12/§8) — Owner-only controls
 * (inviting/deactivating a teammate, assigning a Project) are already
 * proven at the API layer (tests/test_invitations.py, tests/test_users.py,
 * tests/test_project_operations.py) and now by tests/test_rbac_matrix.py's
 * sweep, but no prior test proved a Staff-role *browser session* actually
 * sees these controls absent, not just rejected server-side.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 027 Role Boundary Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint027-role-owner-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint027-role-owner-password-${RUN_ID}`;
const STAFF_EMAIL = `pytest-e2e-sprint027-role-staff-${RUN_ID}@example.invalid`;
const STAFF_NAME = `Pytest E2E Sprint 027 Staff ${RUN_ID}`;
const STAFF_PASSWORD = `pytest-e2e-sprint027-role-staff-password-${RUN_ID}`;
const PROJECT_NAME = `Pytest E2E Sprint 027 Role Boundary Project ${RUN_ID}`;

test("a_staff_session_sees_owner_only_controls_absent_not_merely_rejected", async ({ page }) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Setup through the real API ----
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

  // Real Staff user via a real invitation accept (same mechanism as
  // e2e/project-operations.spec.ts), not a direct DB insert.
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
  const booked = await api.patch(`/api/v1/projects/${projectId}/status`, {
    headers: ownerHeaders,
    data: { status: "quoted" },
  });
  expect(booked.ok()).toBeTruthy();
  const bookedTwo = await api.patch(`/api/v1/projects/${projectId}/status`, {
    headers: ownerHeaders,
    data: { status: "booked" },
  });
  expect(bookedTwo.ok()).toBeTruthy();

  // ---- Authenticate as Staff through the real login UI ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(STAFF_EMAIL);
  await page.getByLabel("Password").fill(STAFF_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // ---- /settings: no invite/team-management controls for Staff ----
  //
  // Sprint 036 turned Settings into sections. The Owner-only ones are now
  // hidden from a Staff session rather than replaced by an explanatory
  // sentence, so this asserts their absence — including when the section
  // is asked for explicitly in the URL, which must not be a way round the
  // gate. The contract is unchanged and if anything stronger.
  await page.goto("/settings?section=team");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  // Scoped to the settings navigation: "Notifications" also names the
  // top bar's bell button, and an unscoped match would be ambiguous.
  const sectionNav = page.getByRole("navigation", { name: "Settings sections" });
  await expect(sectionNav.getByRole("button", { name: /team & permissions/i })).toHaveCount(0);
  await expect(sectionNav.getByRole("button", { name: /billing & subscription/i })).toHaveCount(0);
  await expect(sectionNav.getByRole("button", { name: /^company$/i })).toHaveCount(0);
  await expect(page.getByLabel("Email", { exact: true })).not.toBeVisible();
  await expect(page.getByRole("button", { name: /create invite/i })).not.toBeVisible();

  // ...and the sections that ARE theirs still work.
  await expect(sectionNav.getByRole("button", { name: /notifications/i })).toBeVisible();
  await expect(sectionNav.getByRole("button", { name: /security/i })).toBeVisible();

  // ---- Project detail: no Assign control for Staff (Owner-only, per
  // apps/web/app/projects/[id]/page.tsx's canAssign = role === "Owner") ----
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Project Operations", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Assigned to")).not.toBeVisible();

  await api.dispose();
});
