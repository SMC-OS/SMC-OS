import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 024 — true browser E2E for stale-enquiry follow-up automation.
 * Structural twin of e2e/project-operations.spec.ts (Sprint 023). Setup
 * (tenant, Owner, Project) goes through the real API directly; the
 * automation itself runs through the real CLI entrypoint
 * (app/jobs/follow_up.py) as a real subprocess against the same database
 * the running FastAPI server uses — not a direct Python import, not a
 * mock. The critical user-facing behaviors — seeing the notification,
 * navigating from it, and its read state persisting — run through the
 * real Chromium browser against the real Next.js app and real FastAPI
 * server (see playwright.config.ts's webServer). No wall-clock waiting:
 * --now is the CLI's own documented verification escape hatch
 * (docs/SPRINTS/sprint-024.md §11), not a product-code test seam.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 024 Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint024-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint024-password-${RUN_ID}`;
const PROJECT_NAME = `Pytest E2E Sprint 024 Project ${RUN_ID}`;

function runFollowUpAutomation(now: string): { examined: number; created: number } {
  const output = execFileSync("python", ["-m", "app.jobs.follow_up", "--now", now], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return JSON.parse(output.trim().split("\n").pop() as string);
}

test("a_stale_enquiry_notification_is_created_shown_navigable_and_deduplicated", async ({
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
  const project = await projectRes.json();
  expect(project.status_role).toBe("lead");

  // 8 days after the Project's own creation — past the locked 7-day
  // threshold, evaluated via the CLI's --now override instead of waiting.
  const createdAt = new Date(project.created_at);
  const staleNow = new Date(createdAt.getTime() + 8 * 24 * 60 * 60 * 1000).toISOString();

  // ---- Run the real automation entrypoint (real subprocess, real DB) ----
  const firstRun = runFollowUpAutomation(staleNow);
  expect(firstRun.created).toBeGreaterThanOrEqual(1);

  // ---- Authenticate through the real login UI ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  // ---- See the notification and its unread state through the real UI ----
  const bell = page.getByRole("button", { name: "Notifications" });
  await expect(bell).toBeVisible();
  await bell.click();
  const notificationButton = page.getByRole("button", { name: /enquiry needs follow-up/i });
  await expect(notificationButton).toBeVisible();
  await expect(page.getByText(PROJECT_NAME)).toBeVisible();

  // ---- Click it: verify real navigation to the Project, and mark-read ----
  const markReadResponsePromise = page.waitForResponse(
    (res) => res.url().includes("/api/v1/notifications/") && res.request().method() === "PATCH"
  );
  await notificationButton.click();
  const markReadResponse = await markReadResponsePromise;
  expect(markReadResponse.status()).toBe(200);
  expect((await markReadResponse.json()).read).toBe(true);

  await expect(page).toHaveURL(new RegExp(`/projects/${project.id}$`));
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(PROJECT_NAME)).toBeVisible();

  // ---- Reload: verify the read state persisted server-side ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await bell.click();
  // Re-open shows no unread badge dot for this notification anymore —
  // asserted via the live API below (server-side truth), not just the UI.
  const notificationsAfterReload = await api.get("/api/v1/notifications", {
    headers: authHeaders,
  });
  expect(notificationsAfterReload.ok()).toBeTruthy();
  const persisted = (await notificationsAfterReload.json()).find(
    (n: { source_id: string }) => n.source_id === project.id
  );
  expect(persisted.read).toBe(true);
  expect(persisted.recipient_user_id).toBeTruthy();
  expect(persisted.source_type).toBe("project");

  // ---- Run the automation again: verify no duplicate ----
  const secondRun = runFollowUpAutomation(staleNow);
  expect(secondRun.created).toBe(0);

  const notificationsAfterSecondRun = await api.get("/api/v1/notifications", {
    headers: authHeaders,
  });
  expect(notificationsAfterSecondRun.ok()).toBeTruthy();
  const matchingNotifications = (await notificationsAfterSecondRun.json()).filter(
    (n: { source_id: string }) => n.source_id === project.id
  );
  expect(matchingNotifications).toHaveLength(1);

  await api.dispose();
});
