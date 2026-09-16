import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.14/§7) — the centrepiece of
 * this sprint. Sprints 020-026 each shipped and proved one vertical slice
 * of the v1.0 journey in isolation (6 existing specs in this directory,
 * each its own tenant, each its own single behavior). Nothing before this
 * spec ever proved the slices work *connected*, through the real browser,
 * as one continuous staff + customer journey:
 *
 *   Signup -> Customer -> Project/Enquiry -> Appointment -> Quote ->
 *   Approval -> Project handoff -> Assignment/status operations ->
 *   Documents -> Customer portal -> Messaging -> Follow-up notification ->
 *   Command Centre -> Portal revocation.
 *
 * One RUN_ID-seeded tenant/customer/project is carried through every
 * step below, deliberately *not* isolated per step (unlike every other
 * spec in this directory) — the point here is proving hand-off between
 * modules, not proving isolation (isolation is proven separately by
 * e2e/cross-tenant-boundary.spec.ts). Setup that has no UI path yet
 * (a second, backdated stale-enquiry Project for the follow-up step, and
 * invoking the follow-up CLI job itself) stays API/subprocess-driven,
 * matching every prior spec's own precedent for what has no UI yet.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 027 Journey Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint027-journey-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint027-journey-password-${RUN_ID}`;
const STAFF_EMAIL = `pytest-e2e-sprint027-journey-staff-${RUN_ID}@example.invalid`;
const STAFF_NAME = `Pytest E2E Sprint 027 Journey Staff ${RUN_ID}`;
const STAFF_PASSWORD = `pytest-e2e-sprint027-journey-staff-password-${RUN_ID}`;
const CUSTOMER_NAME = `Pytest E2E Sprint 027 Journey Customer ${RUN_ID}`;
const CUSTOMER_EMAIL = `pytest-e2e-sprint027-journey-customer-${RUN_ID}@example.invalid`;
const PROJECT_NAME = `Pytest E2E Sprint 027 Journey Project ${RUN_ID}`;
const STALE_PROJECT_NAME = `Pytest E2E Sprint 027 Journey Stale Enquiry ${RUN_ID}`;

// Sprint 039 Production Readiness Defect Gate, Blocker 1 — see
// e2e/project-operations.spec.ts's identical helper for the full
// rationale (inviting a teammate now requires a verified email).
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

function runFollowUpAutomation(now: string): { examined: number; created: number } {
  // Same real-subprocess pattern as e2e/follow-up-automation.spec.ts —
  // --now is app/jobs/follow_up.py's own documented verification-only
  // escape hatch, not a test-only seam.
  const output = execFileSync("python", ["-m", "app.jobs.follow_up", "--now", now], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
  });
  return JSON.parse(output.trim().split("\n").pop() as string);
}

test.setTimeout(180_000);

test("the_connected_v1_journey_works_end_to_end_through_the_browser", async ({ browser, page }) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ==== 1. Signup through the real UI (no prior spec ever did this) ====
  await page.goto("/signup");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Company name").fill(COMPANY_NAME);
  await page.getByLabel("Your name").fill("Pytest E2E Journey Owner");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(OWNER_PASSWORD);
  await page.getByLabel("Confirm password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: /create workspace/i }).click();

  // Sprint 036 (Workstream J) — a brand-new workspace now lands on
  // onboarding rather than an empty customer list. The setup flow is
  // entirely skippable, which is what this journey does: it is here to
  // prove the lead-to-project pipeline, not the wizard, and a setup step
  // that could not be skipped would be a defect in its own right.
  await expect(page).toHaveURL(/\/onboarding$/, { timeout: 15_000 });
  await page.getByRole("button", { name: /^skip$/i }).first().click();
  await page.getByRole("button", { name: /^skip$/i }).first().click();
  await page.getByRole("button", { name: /^skip$/i }).first().click();
  await page.getByRole("button", { name: /go to geocore/i }).click();
  await expect(page).toHaveURL(/localhost:3000\/$/, { timeout: 15_000 });

  // ==== 2. Session persists across a reload ====
  await page.reload();
  await page.waitForLoadState("networkidle");
  // Onboarding is complete now, so the dashboard stays put rather than
  // bouncing back to setup — the regression that would matter most here.
  await expect(page).toHaveURL(/localhost:3000\/$/, { timeout: 15_000 });

  const ownerLogin = await api.post("/api/v1/auth/login", {
    data: { email: OWNER_EMAIL, password: OWNER_PASSWORD },
  });
  expect(ownerLogin.ok()).toBeTruthy();
  const ownerHeaders = { Authorization: `Bearer ${(await ownerLogin.json()).access_token}` };
  await verifyOwnerEmail(api, OWNER_EMAIL);

  // A real Staff user, via a real invitation accept — needed for step 8.
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

  // ==== 3. Create a Customer through the UI ====
  await page.goto("/customers/new");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Full name").fill(CUSTOMER_NAME);
  await page.getByLabel("Email").fill(CUSTOMER_EMAIL);
  await page.getByRole("button", { name: "Save customer" }).click();
  await expect(page).toHaveURL(/\/customers\/[0-9a-f-]+$/, { timeout: 15_000 });
  const customerId = page.url().match(/\/customers\/([0-9a-f-]+)$/)![1];

  // ==== 4. Create a Project (enquiry) linked to that Customer ====
  await page.goto("/projects/new");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Project name").fill(PROJECT_NAME);
  await page.getByLabel("Customer").selectOption({ label: CUSTOMER_NAME });
  await page.getByRole("button", { name: /save project|create project/i }).click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/, { timeout: 15_000 });
  await expect(page.getByText("Enquiry", { exact: true })).toBeVisible();

  // ==== 5. Schedule and complete a site visit ====
  await expect(page.getByText("Site Visits", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Schedule Site Visit" }).click();
  await page.getByLabel("Date & time").fill("2030-06-15T10:30");
  const appointmentCreated = page.waitForResponse(
    (res) => res.url().includes("/appointments") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Save site visit" }).click();
  await appointmentCreated;
  await expect(page.getByText("scheduled", { exact: true })).toBeVisible();
  const completeButton = page.getByRole("button", { name: "Complete" });
  await expect(completeButton).toBeVisible();
  const appointmentCompleted = page.waitForResponse(
    (res) => /\/appointments\/[0-9a-f-]+\/status$/.test(res.url()) && res.request().method() === "PATCH"
  );
  await completeButton.click();
  await appointmentCompleted;
  await expect(page.getByText("completed", { exact: true })).toBeVisible();

  // ==== 6. Create a Quote linked to the Customer; approve it ====
  await page.goto("/quotes/new/stone");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Link to existing customer (optional)").selectOption({
    label: CUSTOMER_NAME,
  });
  await page.getByLabel("Length (mm)").fill("3200");
  const quoteCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/quote") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Calculate Quote" }).click();
  const quoteResponse = await quoteCreated;
  expect(quoteResponse.status()).toBe(200);
  const quoteId = (await quoteResponse.json()).id as string;

  await page.goto(`/quotes/${quoteId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  const approveResponse = page.waitForResponse(
    (res) => res.url().endsWith(`/api/v1/quotes/${quoteId}/approve`) && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Approve" }).click();
  await approveResponse;
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();

  // ==== 7. Turn the approved Quote into the Project ====
  const handoffResponse = page.waitForResponse(
    (res) => res.url().endsWith(`/api/v1/quotes/${quoteId}/handoff`) && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Create the project" }).click();
  const handoff = await handoffResponse;
  expect(handoff.status()).toBe(200);
  const handedOffProject = await handoff.json();
  expect(handedOffProject.status).toBe("booked");
  await expect(page.getByText("Booked", { exact: true })).toBeVisible();

  // ==== 8. Assignment + status operations on the handed-off Project ====
  await page.goto(`/projects/${handedOffProject.id}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Project Operations", { exact: true })).toBeVisible();
  const assignResponse = page.waitForResponse(
    (res) => res.url().endsWith(`/api/v1/projects/${handedOffProject.id}/assign`) && res.request().method() === "PATCH"
  );
  await page.getByLabel("Assigned to").selectOption({ label: STAFF_NAME });
  await assignResponse;

  for (const nextLabel of ["Templated", "Fabricated", "Installed", "Complete"]) {
    const advanceButton = page.getByRole("button", { name: `Advance to ${nextLabel}` });
    await expect(advanceButton).toBeVisible();
    const statusResponse = page.waitForResponse(
      (res) => res.url().endsWith(`/api/v1/projects/${handedOffProject.id}/status`) && res.request().method() === "PATCH"
    );
    await advanceButton.click();
    await statusResponse;
    await expect(page.getByText(nextLabel, { exact: true })).toBeVisible();
  }

  // ==== 9. Upload a Document to the Customer ====
  await page.goto(`/customers/${customerId}`);
  await page.waitForLoadState("networkidle");
  const tmpFile = path.join(os.tmpdir(), `sprint027-journey-${RUN_ID}.txt`);
  fs.writeFileSync(tmpFile, `Sprint 027 full-system journey document ${RUN_ID}`);
  const documentUploaded = page.waitForResponse(
    (res) => res.url().includes("/api/v1/documents?") && res.request().method() === "POST"
  );
  await page.locator('input[type="file"]').setInputFiles(tmpFile);
  const uploadResponse = await documentUploaded;
  expect(uploadResponse.status()).toBe(201);
  await expect(page.getByText(`sprint027-journey-${RUN_ID}.txt`)).toBeVisible();

  // ==== 10. Portal link + customer portal view, in a second, ====
  // ====     unauthenticated browser context                 ====
  const portalLinkCreated = page.waitForResponse(
    (res) => res.url().endsWith("/api/v1/portal-links") && res.request().method() === "POST"
  );
  await page.getByRole("button", { name: "Generate portal link" }).click();
  const portalLinkResponse = await portalLinkCreated;
  const portalLink = await portalLinkResponse.json();

  const customerContext = await browser.newContext();
  const customerPage = await customerContext.newPage();
  await customerPage.goto(`/portal/${portalLink.token}`);
  await customerPage.waitForLoadState("networkidle");
  await expect(customerPage.getByText(PROJECT_NAME)).toBeVisible();
  await expect(customerPage.getByText(`sprint027-journey-${RUN_ID}.txt`)).toBeVisible();

  // ==== 11. Messaging — customer sends, staff sees and replies ====
  const customerMessagePosted = customerPage.waitForResponse(
    (res) => res.url().includes("/messages") && res.request().method() === "POST"
  );
  await customerPage.getByPlaceholder("Write a message…").fill("When can you start?");
  await customerPage.getByRole("button", { name: /^send$/i }).click();
  await customerMessagePosted;
  await expect(customerPage.getByText("When can you start?")).toBeVisible();

  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("When can you start?")).toBeVisible();

  // ==== 12. Follow-up notification, via a separately-seeded stale ====
  // ====     enquiry Project. (RED finding: quote handoff creates a ====
  // ====     *new* Project — app/quotes/service.py's handoff() — so ====
  // ====     the Project created in step 4 stays in `enquiry` for  ====
  // ====     this test's whole run too, and is independently stale ====
  // ====     by this point. Left unassigned like this one, so both ====
  // ====     fall back to the Owner and both are visible below —   ====
  // ====     this assertion only needs *a* notification containing ====
  // ====     STALE_PROJECT_NAME, not that it's the only one.)      ====
  const staleProjectRes = await api.post("/api/v1/projects", {
    headers: ownerHeaders,
    data: { name: STALE_PROJECT_NAME },
  });
  expect(staleProjectRes.ok()).toBeTruthy();
  const staleProjectId = (await staleProjectRes.json()).id as string;

  // STALE_ENQUIRY_THRESHOLD (app/notifications/follow_up_service.py) is 7
  // days; 30 days ahead is comfortably past it regardless of the
  // threshold's exact value.
  const farFuture = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
  const followUpResult = runFollowUpAutomation(farFuture);
  expect(followUpResult.created).toBeGreaterThanOrEqual(1);

  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  const notificationsButton = page.getByRole("button", { name: /notifications/i });
  await notificationsButton.click();
  await expect(page.getByText(STALE_PROJECT_NAME)).toBeVisible();
  await page.getByText(STALE_PROJECT_NAME).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${staleProjectId}$`), { timeout: 15_000 });

  // ==== 13. Command Centre reflects the state built above ====
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Business Command Centre")).toBeVisible();
  // Same scoping technique as e2e/business-command-centre.spec.ts: an
  // unscoped page-wide getByText("Handed off") could also match
  // RecentActivityPanel's own "Quote handed off" entry on the same page.
  const commandCentre = page
    .getByRole("heading", { name: "Business Command Centre" })
    .locator("xpath=..");
  await expect(commandCentre.getByText("Handed off", { exact: true })).toBeVisible();

  // ==== 14. Revoke the portal link; the customer context sees it die ====
  const revokeResponse = page.waitForResponse(
    (res) => res.url().includes("/portal-links/") && res.request().method() === "DELETE"
  );
  await page.goto(`/customers/${customerId}`);
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Revoke" }).click();
  await revokeResponse;

  await customerPage.reload();
  await customerPage.waitForLoadState("networkidle");
  await expect(customerPage.getByText(/This link has been revoked/)).toBeVisible();

  await customerContext.close();
  await api.dispose();
});
