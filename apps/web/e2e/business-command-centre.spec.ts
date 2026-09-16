import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * Sprint 025 — true browser E2E for the Business Command Centre. Structural
 * twin of e2e/follow-up-automation.spec.ts (Sprint 024). Setup goes through
 * the real API directly (not TestClient, not mocked); the stale-enquiry
 * follow-up notification is created through the real CLI entrypoint
 * (app/jobs/follow_up.py) as a real subprocess against the same database
 * the running FastAPI server uses. The dashboard read itself runs through
 * the real Chromium browser against the real Next.js app and real FastAPI
 * server (see playwright.config.ts's webServer). No mocks anywhere in this
 * spec.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 025 Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint025-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint025-password-${RUN_ID}`;

const OTHER_COMPANY_NAME = `Pytest E2E Sprint 025 Other Co ${RUN_ID}`;
const OTHER_OWNER_EMAIL = `pytest-e2e-sprint025-other-${RUN_ID}@example.invalid`;
const OTHER_OWNER_PASSWORD = `pytest-e2e-sprint025-other-password-${RUN_ID}`;

function formatCurrencyGBP(value: number): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    maximumFractionDigits: 0,
  }).format(value);
}

function runFollowUpAutomation(now: string): { created: number } {
  const output = execFileSync("python", ["-m", "app.jobs.follow_up", "--now", now], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return JSON.parse(output.trim().split("\n").pop() as string);
}

test("business_command_centre_shows_exact_controlled_metrics_and_excludes_other_tenants", async ({
  page,
}) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Tenant A: signup (real API) ----
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
  const { access_token: token } = await signup.json();
  const headers = { Authorization: `Bearer ${token}` };

  // ---- Tenant B: a second, fully separate tenant, whose data must never
  // appear in Tenant A's Command Centre ----
  const otherSignup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: OTHER_COMPANY_NAME,
      name: "Pytest E2E Other Owner",
      email: OTHER_OWNER_EMAIL,
      password: OTHER_OWNER_PASSWORD,
    },
  });
  expect(otherSignup.ok()).toBeTruthy();
  markVerified(OTHER_OWNER_EMAIL);
  const { access_token: otherToken } = await otherSignup.json();
  const otherHeaders = { Authorization: `Bearer ${otherToken}` };
  const otherProject = await api.post("/api/v1/projects", {
    headers: otherHeaders,
    data: { name: `${OTHER_COMPANY_NAME} Project` },
  });
  expect(otherProject.ok()).toBeTruthy();

  // ---- Pipeline: two Projects stay "enquiry", one walked to "quoted" ----
  const staleProjectRes = await api.post("/api/v1/projects", {
    headers,
    data: { name: `${COMPANY_NAME} Stale Enquiry Project` },
  });
  expect(staleProjectRes.ok()).toBeTruthy();
  const staleProject = await staleProjectRes.json();

  const secondEnquiryRes = await api.post("/api/v1/projects", {
    headers,
    data: { name: `${COMPANY_NAME} Second Enquiry Project` },
  });
  expect(secondEnquiryRes.ok()).toBeTruthy();

  const quotedProjectRes = await api.post("/api/v1/projects", {
    headers,
    data: { name: `${COMPANY_NAME} Quoted Project` },
  });
  expect(quotedProjectRes.ok()).toBeTruthy();
  const quotedProject = await quotedProjectRes.json();
  const toQuoted = await api.patch(`/api/v1/projects/${quotedProject.id}/status`, {
    headers,
    data: { status: "quoted" },
  });
  expect(toQuoted.ok()).toBeTruthy();

  // ---- Site visits: 3 Appointments on the "quoted" Project ----
  const scheduledAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
  const appointmentIds: string[] = [];
  for (let i = 0; i < 3; i += 1) {
    const res = await api.post(`/api/v1/projects/${quotedProject.id}/appointments`, {
      headers,
      data: { scheduled_at: scheduledAt },
    });
    expect(res.ok()).toBeTruthy();
    appointmentIds.push((await res.json()).id);
  }
  const completeAppt = await api.patch(`/api/v1/appointments/${appointmentIds[0]}/status`, {
    headers,
    data: { status: "completed" },
  });
  expect(completeAppt.ok()).toBeTruthy();
  const cancelAppt = await api.patch(`/api/v1/appointments/${appointmentIds[1]}/status`, {
    headers,
    data: { status: "cancelled" },
  });
  expect(cancelAppt.ok()).toBeTruthy();
  // appointmentIds[2] stays "scheduled".

  // ---- Quote funnel + value: draft, approved, approved-and-handed-off ----
  const customerRes = await api.post("/api/v1/customers", {
    headers,
    data: { name: `${COMPANY_NAME} Customer` },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customer = await customerRes.json();

  async function createDraftQuote(postcode: string) {
    const res = await api.post("/api/v1/quote", {
      headers,
      data: {
        customer: `${COMPANY_NAME} Customer`,
        customer_id: customer.id,
        material: "Calacatta Gold",
        thickness: "20mm",
        kitchen_length: 3.0,
        postcode,
      },
    });
    expect(res.ok()).toBeTruthy();
    return res.json();
  }

  const draftQuote = await createDraftQuote(`S025E2E-DRAFT-${RUN_ID}`);
  const approvedQuote = await createDraftQuote(`S025E2E-APPROVED-${RUN_ID}`);
  const approveRes = await api.post(`/api/v1/quotes/${approvedQuote.id}/approve`, { headers });
  expect(approveRes.ok()).toBeTruthy();

  const handoffQuote = await createDraftQuote(`S025E2E-HANDOFF-${RUN_ID}`);
  const approveHandoffRes = await api.post(`/api/v1/quotes/${handoffQuote.id}/approve`, {
    headers,
  });
  expect(approveHandoffRes.ok()).toBeTruthy();
  const handoffRes = await api.post(`/api/v1/quotes/${handoffQuote.id}/handoff`, { headers });
  expect(handoffRes.ok()).toBeTruthy();

  const expectedQuotedValue = draftQuote.total + approvedQuote.total + handoffQuote.total;
  const expectedApprovedValue = approvedQuote.total + handoffQuote.total;

  // ---- Follow-up attention: real automation CLI, 8 days past the stale
  // Project's own creation, past the locked 7-day threshold. The
  // automation scans globally across every tenant (docs/SPRINTS/
  // sprint-024.md §6), so `created` can exceed 2 if other tenants in this
  // shared dev database also have stale enquiries — same reasoning as
  // e2e/follow-up-automation.spec.ts's >=1 assertion. What's exact and
  // tenant-scoped is the Command Centre's own follow_up count below, not
  // this global job-return count. Both unassigned "enquiry" Projects
  // created above (staleProject and secondEnquiryRes) are equally stale
  // relative to staleNow, so at least 2 of the created notifications are
  // ours. ----
  const staleCreatedAt = new Date(staleProject.created_at);
  const staleNow = new Date(staleCreatedAt.getTime() + 8 * 24 * 60 * 60 * 1000).toISOString();
  const automationRun = runFollowUpAutomation(staleNow);
  expect(automationRun.created).toBeGreaterThanOrEqual(2);

  // ---- Expected Command Centre response, computed from the controlled
  // dataset above (docs/SPRINTS/sprint-025.md §3's exact semantics) ----
  const expected = {
    customers: 1,
    pipeline: {
      enquiry: 2,
      quoted: 1,
      booked: 1, // created by the handoff above, not by a manual PATCH
      templated: 0,
      fabricated: 0,
      installed: 0,
      complete: 0,
    },
    quotes: { draft: 1, approved: 2, handed_off: 1 },
    site_visits: { scheduled: 1, completed: 1, cancelled: 1 },
    follow_up: { unread_follow_ups: 2 },
  };

  // ---- Live API cross-check, independent of the UI ----
  const apiCommandCentre = await api.get("/api/v1/dashboard/command-centre", { headers });
  expect(apiCommandCentre.ok()).toBeTruthy();
  const apiBody = await apiCommandCentre.json();
  expect(apiBody.customers).toBe(expected.customers);
  expect(apiBody.pipeline).toEqual(expected.pipeline);
  expect(apiBody.quotes).toEqual(expected.quotes);
  expect(apiBody.site_visits).toEqual(expected.site_visits);
  expect(apiBody.follow_up).toEqual(expected.follow_up);
  expect(apiBody.value.quoted_value).toBeCloseTo(expectedQuotedValue, 2);
  expect(apiBody.value.approved_quoted_value).toBeCloseTo(expectedApprovedValue, 2);

  // Tenant B's own command centre must never see Tenant A's counts.
  const otherCommandCentre = await api.get("/api/v1/dashboard/command-centre", {
    headers: otherHeaders,
  });
  expect(otherCommandCentre.ok()).toBeTruthy();
  const otherBody = await otherCommandCentre.json();
  expect(otherBody.pipeline.enquiry).toBe(1); // only otherProject, not Tenant A's
  expect(otherBody.quotes).toEqual({ draft: 0, approved: 0, handed_off: 0 });
  // Not asserting follow_up here: otherProject is itself an unassigned
  // "enquiry" Project created moments before staleProject, so it is
  // equally stale relative to staleNow and legitimately picks up its own
  // notification from the automation's global scan (docs/SPRINTS/
  // sprint-024.md §6) — that's correct behavior, not a tenant-isolation
  // leak. Pipeline/quotes above already prove Tenant A's counts don't
  // appear in Tenant B's response, which is the isolation contract this
  // spec exists to cover.

  // ---- Real browser flow ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/customers$/);

  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Business Command Centre")).toBeVisible();

  // Scoped to the Command Centre section itself (CommandCentrePanel's
  // own root div — the direct parent of its "Business Command Centre"
  // heading): the pre-existing StatGrid "Revenue" card (from
  // GET /dashboard, out of this sprint's scope) sums the same all-quotes
  // total under a different label, so an unscoped page-wide
  // getByText(£...) can ambiguously match both.
  const commandCentre = page
    .getByRole("heading", { name: "Business Command Centre" })
    .locator("xpath=..");

  const pipelineCard = commandCentre.locator("div", { hasText: "Pipeline" }).first();
  await expect(pipelineCard).toBeVisible();

  // Exact match: RecentActivityPanel also renders a "Quote handed off"
  // activity entry on this same page, which getByText("Handed off")
  // (substring match) would ambiguously match too.
  await expect(commandCentre.getByText("Handed off", { exact: true })).toBeVisible();
  await expect(commandCentre.getByText(formatCurrencyGBP(expectedQuotedValue))).toBeVisible();
  await expect(commandCentre.getByText(formatCurrencyGBP(expectedApprovedValue))).toBeVisible();
  await expect(commandCentre.getByText("2 unread")).toBeVisible();

  // ---- Reload: values must persist (real server data, not client state) ----
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Business Command Centre")).toBeVisible();
  await expect(commandCentre.getByText(formatCurrencyGBP(expectedQuotedValue))).toBeVisible();
  await expect(commandCentre.getByText("2 unread")).toBeVisible();

  // Tenant B's project name must never leak into Tenant A's rendered page.
  await expect(page.getByText(`${OTHER_COMPANY_NAME} Project`)).toHaveCount(0);

  await api.dispose();
});
