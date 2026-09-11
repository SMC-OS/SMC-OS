import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

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
const OWNER_PASSWORD = `pytest-e2e-sprint039-verify-password-${RUN_ID}`;
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

test("signup_shows_unverified_then_confirming_the_emailed_link_verifies_the_account", async ({
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
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/(customers|onboarding)/);

  // ---- Settings → Security shows the real unverified state ----
  await page.goto("/settings?section=security");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Unverified")).toBeVisible();
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

  // ---- Settings → Security now reflects the real verified state ----
  await page.goto("/settings?section=security");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Verified")).toBeVisible();
  await expect(page.getByRole("button", { name: "Resend verification email" })).toHaveCount(0);

  await api.dispose();
});

test("an_unverified_owner_cannot_invite_a_teammate_and_a_verified_one_can", async ({ page }) => {
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
  await expect(page).toHaveURL(/\/(customers|onboarding)/);

  // ---- Blocked while unverified (server-side, not merely UI copy) ----
  await page.goto("/settings?section=team");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(`pytest-invitee-${RUN_ID}@example.invalid`);
  await page.getByRole("button", { name: "Create invite" }).click();
  await expect(page.getByText(/verify your email address/i)).toBeVisible();

  // ---- Verify, then the same action succeeds ----
  const rawToken = mintVerificationToken(email);
  await page.goto(`/verify-email?token=${rawToken}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Your email address has been verified.")).toBeVisible();

  await page.goto("/settings?section=team");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(`pytest-invitee-${RUN_ID}@example.invalid`);
  await page.getByRole("button", { name: "Create invite" }).click();
  await expect(page.getByText("Joining link for")).toBeVisible();

  await api.dispose();
});
