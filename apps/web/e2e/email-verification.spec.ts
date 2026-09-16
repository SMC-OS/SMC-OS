import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { grantBillingAccess } from "./billing-helper";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 1 — true browser
 * E2E for email verification. Structural twin of
 * e2e/follow-up-automation.spec.ts: setup (tenant/Owner) goes through the
 * real API directly; the "click the link in the email" step can't run
 * through a real inbox in CI (no live Resend account — see
 * app/communications/provider.py's "ships dark until configured"
 * contract), so a raw token is minted the same way
 * EmailVerificationService.send_verification_email() does (opaque
 * secrets.token_urlsafe(32), sha256-hashed before it's ever persisted) via
 * a real Python subprocess against the same database the running FastAPI
 * server uses — not a mock, not a direct import into the test process.
 * Everything else (signing in, seeing the unverified state, confirming,
 * seeing the verified state) runs through the real Chromium browser
 * against the real Next.js app and real FastAPI server.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 039 Verify Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint039-verify-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `Pytest-E2e-Sprint039-Verify-Password-${RUN_ID}!`;
const OWNER_NAME = "Pytest E2E Verify Owner";

function mintVerificationToken(email: string): string {
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
    db,
    id=uuid.uuid4(),
    user_id=user.id,
    token_hash=token_hash,
    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
)
db.close()
print(raw_token)
`.trim();
  const output = execFileSync("python", ["-c", script], { cwd: REPO_ROOT, encoding: "utf-8" });
  return output.trim().split("\n").pop() as string;
}

test("signup_lands_on_verify_email_and_confirming_the_emailed_link_unlocks_the_workspace", async ({
  page,
}) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  // ---- Setup through the real API (not TestClient, not mocked) ----
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: COMPANY_NAME,
      name: OWNER_NAME,
      email: OWNER_EMAIL,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();

  // ---- Sign in through the real login UI ----
  // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — an
  // unverified account no longer lands in the workspace at all; it's
  // redirected to the verification-required screen before it ever sees
  // Dashboard/Customers/Onboarding.
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/verify-email/);
  await expect(page.getByText(OWNER_EMAIL)).toBeVisible();

  // ---- Directly navigating to a protected page redirects back here too
  // (the gate is not just "don't show a link to it") ----
  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/verify-email/);

  // ---- Resend, from the verification screen itself ----
  const resendButton = page.getByRole("button", { name: "Resend verification email" });
  await expect(resendButton).toBeVisible();
  await resendButton.click();
  await expect(page.getByText(/verification email sent/i)).toBeVisible();

  // ---- Confirm via the real link target, with a token minted the same
  // way the real email would have (see mintVerificationToken's docstring
  // above) ----
  const rawToken = mintVerificationToken(OWNER_EMAIL);
  await page.goto(`/verify-email?token=${rawToken}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Your email address has been verified.")).toBeVisible();
  // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES — this spec's subject is
  // email verification, not billing activation itself (that's
  // billing-pricing.spec.ts), so it grants billing access explicitly
  // here, the same "not this test's subject" reasoning applied
  // throughout this suite, rather than routing through a real
  // (unconfigured-in-this-sandbox) Stripe Checkout. That grant happens
  // server-side, after this browser's AuthProvider already cached its
  // pre-grant state — same "needs a fresh navigation to re-fetch
  // /auth/me" requirement Sprint 039 Blocker 2's own fixture fixes
  // established, so a direct goto is used below instead of the in-app
  // client-side "Continue to GeoCore" click.
  grantBillingAccess(OWNER_EMAIL);
  await page.goto("/customers");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/customers/);

  // ---- Settings → Security now reflects the real verified state, and
  // normal workspace navigation is no longer redirected ----
  await page.goto("/settings?section=security");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/settings/);
  await expect(page.getByText("Verified")).toBeVisible();
  await expect(page.getByRole("button", { name: "Resend verification email" })).toHaveCount(0);

  await api.dispose();
});

test("login_for_an_existing_unverified_account_cannot_bypass_verification", async ({ page }) => {
  const email = `pytest-e2e-sprint039-verify-relogin-${RUN_ID}@example.invalid`;
  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 039 Relogin Co ${RUN_ID}`,
      name: OWNER_NAME,
      email,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();

  // First sign-in already redirects to /verify-email (previous test).
  // This test's own subject is the SECOND sign-in of an account that is
  // still unverified — logging out and back in must not be a bypass.
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/verify-email/);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/verify-email/);

  await api.dispose();
});

test("an_unverified_owner_cannot_reach_team_settings_or_invite_a_teammate_and_a_verified_one_can", async ({
  page,
}) => {
  const email = `pytest-e2e-sprint039-verify-invite-${RUN_ID}@example.invalid`;
  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 039 Invite Co ${RUN_ID}`,
      name: OWNER_NAME,
      email,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/verify-email/);

  // ---- Blocked at the door, not just at the invite button (server-side
  // boundary, not merely UI copy — Sprint 039 Blocker 2 hotfix widens
  // this from "invite a teammate" specifically to every normal route) ----
  await page.goto("/settings?section=team");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/verify-email/);

  // ---- Verify, then the same page and action succeed ----
  const rawToken = mintVerificationToken(email);
  await page.goto(`/verify-email?token=${rawToken}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Your email address has been verified.")).toBeVisible();
  // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES — this spec's subject is
  // email verification unlocking access, not billing activation itself.
  // Safe to grant here, before the goto below: that's a hard navigation
  // (unlike an in-app button click), so it picks up this fresh state.
  grantBillingAccess(email);

  await page.goto("/settings?section=team");
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveURL(/\/settings/);
  await page.getByLabel("Email").fill(`pytest-invitee-${RUN_ID}@example.invalid`);
  await page.getByRole("button", { name: "Create invite" }).click();
  await expect(page.getByText("Joining link for")).toBeVisible();

  await api.dispose();
});

test("replaying_an_already_used_link_shows_already_verified_not_invalid_and_resend_is_honest_about_sending_nothing", async ({
  page,
}) => {
  // Sprint 039 Production Readiness Defect Gate, Blocker 2 follow-up
  // (verification resend/token hotfix) — reproduces the owner's exact
  // live-staging observation: a second view of the same, already-
  // successfully-used link, plus a resend after verification. Real
  // Chromium, real FastAPI, real Postgres — not a unit-level fake.
  const email = `pytest-e2e-sprint039-verify-resend-hotfix-${RUN_ID}@example.invalid`;
  const api = await request.newContext({ baseURL: BACKEND_URL });
  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `Pytest E2E Sprint 039 Resend Hotfix Co ${RUN_ID}`,
      name: OWNER_NAME,
      email,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();

  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/verify-email/);

  const rawToken = mintVerificationToken(email);
  await page.goto(`/verify-email?token=${rawToken}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Your email address has been verified.")).toBeVisible();

  // ---- The owner's exact symptom: view the SAME link again (a mail
  // client reopening it, a double-tap, a link-prescanning proxy). The
  // token replay is still correctly rejected server-side (400) — what
  // changes is that this browser's own live, freshly-fetched auth state
  // now knows the account is verified, so it says so instead of "invalid
  // or expired". ----
  await page.goto(`/verify-email?token=${rawToken}`);
  await page.waitForLoadState("networkidle");
  await expect(
    page.getByText("Your email address is already verified — you're all set.")
  ).toBeVisible();
  await expect(page.getByText(/invalid or has expired/i)).toHaveCount(0);

  // ---- Resend after verification: honest about sending nothing ----
  await page.goto("/verify-email");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Resend verification email" }).click();
  await expect(
    page.getByText("Your email is already verified — you're all set.")
  ).toBeVisible();
  await expect(page.getByText("Verification email sent — check your inbox.")).toHaveCount(0);

  await api.dispose();
});
