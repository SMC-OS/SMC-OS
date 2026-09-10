import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 022 — true browser E2E for site visit scheduling. Structural twin
 * of e2e/enquiry-conversion.spec.ts (Sprint 021). Setup (tenant + Project)
 * goes through the real API directly, but the critical business
 * transitions — scheduling a site visit and marking it completed — run
 * through the real Chromium browser against the real Next.js app and real
 * FastAPI server (see playwright.config.ts's webServer). Nothing here mocks
 * fetch, the router, or the API client; page.waitForResponse below only
 * observes the real network response, it never intercepts or fulfills it.
 */

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 022 Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint022-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint022-password-${RUN_ID}`;
const PROJECT_NAME = `Pytest E2E Sprint 022 Project ${RUN_ID}`;
const NOTES = `Pytest E2E Sprint 022 Notes ${RUN_ID}`;

test("a_site_visit_can_be_scheduled_and_completed_through_the_ui_and_persists", async ({
  page,
}) => {
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
  const { access_token: token } = await signup.json();
  const authHeaders = { Authorization: `Bearer ${token}` };

  const projectRes = await api.post("/api/v1/projects", {
    headers: authHeaders,
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

  // ---- Open the real Project detail page ----
  await page.goto(`/projects/${projectId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Site Visits", { exact: true })).toBeVisible();
  await expect(page.getByText("No site visits scheduled yet.")).toBeVisible();
  const scheduleButton = page.getByRole("button", { name: "Schedule Site Visit" });
  await expect(scheduleButton).toBeVisible();

  // ---- Schedule through the UI (not a direct API call) ----
  await scheduleButton.click();
  await page.getByLabel("Date & time").fill("2030-06-15T10:30");
  await page.getByLabel("Notes").fill(NOTES);

  const createResponsePromise = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/projects/${projectId}/appointments`) &&
      res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Save site visit" }).click();
  const createResponse = await createResponsePromise;
  expect(createResponse.status()).toBe(201);
  const createdAppointment = await createResponse.json();
  expect(createdAppointment.id).toBeTruthy();
  expect(createdAppointment.status).toBe("scheduled");

  // ---- Verify the real Project page reflects the returned Appointment ----
  await expect(page.getByText(NOTES)).toBeVisible();
  await expect(page.getByText("scheduled", { exact: true })).toBeVisible();
  const completeButton = page.getByRole("button", { name: "Complete" });
  await expect(completeButton).toBeVisible();

  // ---- Verify persistence: reload proves it was saved, not just client state ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(NOTES)).toBeVisible();
  await expect(page.getByText("scheduled", { exact: true })).toBeVisible();

  // ---- Complete the site visit through the UI ----
  const transitionResponsePromise = page.waitForResponse(
    (res) =>
      res.url().endsWith(`/api/v1/appointments/${createdAppointment.id}/status`) &&
      res.request().method() === "PATCH"
  );
  await page.getByRole("button", { name: "Complete" }).click();
  const transitionResponse = await transitionResponsePromise;
  expect(transitionResponse.status()).toBe(200);
  const completedAppointment = await transitionResponse.json();
  expect(completedAppointment.status).toBe("completed");

  await expect(page.getByText("completed", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Complete" })).not.toBeVisible();
  // `exact: true`: Playwright matches an accessible name by substring by
  // default, and this assertion is about the site visit's own Cancel
  // action — not about every button whose label happens to contain the
  // word (Sprint 039 added "Cancel this job" to the pipeline panel on
  // this same page).
  await expect(
    page.getByRole("button", { name: "Cancel", exact: true })
  ).not.toBeVisible();

  // ---- Verify persistence again after reload ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("completed", { exact: true })).toBeVisible();

  // ---- Verify persisted state through the live API (server-side truth) ----
  const persistedAppointmentsRes = await api.get(
    `/api/v1/projects/${projectId}/appointments`,
    { headers: authHeaders }
  );
  expect(persistedAppointmentsRes.ok()).toBeTruthy();
  const persistedAppointments = await persistedAppointmentsRes.json();
  expect(persistedAppointments).toHaveLength(1);
  expect(persistedAppointments[0].id).toBe(createdAppointment.id);
  expect(persistedAppointments[0].status).toBe("completed");
  expect(persistedAppointments[0].notes).toBe(NOTES);

  // ---- Verify exactly one scheduled and one completed activity exist for
  // this appointment (tenant-scoped: GET /activity is always the caller's
  // own tenant — see app/activity/router.py) ----
  const scheduledActivityRes = await api.get(
    "/api/v1/activity?limit=50&type=site_visit_scheduled",
    { headers: authHeaders }
  );
  expect(scheduledActivityRes.ok()).toBeTruthy();
  const scheduledActivity = await scheduledActivityRes.json();
  const matchingScheduled = scheduledActivity.filter((event: { description: string | null }) =>
    (event.description ?? "").includes(createdAppointment.id)
  );
  expect(matchingScheduled).toHaveLength(1);

  const completedActivityRes = await api.get(
    "/api/v1/activity?limit=50&type=site_visit_completed",
    { headers: authHeaders }
  );
  expect(completedActivityRes.ok()).toBeTruthy();
  const completedActivity = await completedActivityRes.json();
  const matchingCompleted = completedActivity.filter((event: { description: string | null }) =>
    (event.description ?? "").includes(createdAppointment.id)
  );
  expect(matchingCompleted).toHaveLength(1);

  await api.dispose();
});
