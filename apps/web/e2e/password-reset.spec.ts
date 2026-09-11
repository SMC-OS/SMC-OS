import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2 — true browser
 * E2E for password recovery. Structural twin of
 * e2e/email-verification.spec.ts (Blocker 1): setup (tenant/Owner) goes
 * through the real API directly; "click the reset link in the email"
 * can't run through a real inbox in CI (no live Resend account — see
 * app/communications/provider.py's "ships dark until configured"
 * contract), so a raw token is minted the same way
 * PasswordResetService.request_reset() does (opaque
 * secrets.token_urlsafe(32), sha256-hashed before it's ever persisted)
 * via a real Python subprocess against the same database the running
 * FastAPI server uses — not a mock, not a bypass. Everything else (the
 * "Forgot password?" link, filling the form, seeing success/error
 * states, signing in with the new password, confirming the old session
 * is dead) runs through the real Chromium browser against the real
 * Next.js app and real FastAPI server.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 039 Reset Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint039-reset-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `pytest-e2e-sprint039-reset-password-${RUN_ID}`;
const NEW_PASSWORD = `pytest-e2e-sprint039-reset-new-password-${RUN_ID}`;
const OWNER_NAME = "Pytest E2E Reset Owner";

function mintResetToken(email: string): string {
  const script = `
import hashlib, secrets, uuid
from datetime import datetime, timedelta, timezone
from app.database import crud
from app.database.database import SessionLocal

db = SessionLocal()
user = crud.get_user_by_email(db, ${JSON.stringify(email)})
raw_token = secrets.token_urlsafe(32)
token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
crud.create_password_reset_token(
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

test("forgot_password_link_reset_flow_and_old_session_revoked", async ({ page, browser }) => {
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

  // ---- Sign in through the real login UI, keep this session open in its
  // own browser context so we can prove it's revoked after the reset ----
  const oldSessionContext = await browser.newContext();
  const oldSessionPage = await oldSessionContext.newPage();
  await oldSessionPage.goto("/login");
  await oldSessionPage.waitForLoadState("networkidle");
  await oldSessionPage.getByLabel("Email").fill(OWNER_EMAIL);
  await oldSessionPage.getByLabel("Password").fill(OWNER_PASSWORD);
  await oldSessionPage.getByRole("button", { name: "Sign in" }).click();
  await expect(oldSessionPage).toHaveURL(/\/(customers|onboarding)/);

  // ---- The real "Forgot password?" link from the login page ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);

  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByText(/if an account exists for that email/i)).toBeVisible();

  // ---- Confirm via the real link target, with a token minted the same
  // way the real email would have (see mintResetToken's docstring above) ----
  const rawToken = mintResetToken(OWNER_EMAIL);
  await page.goto(`/reset-password?token=${rawToken}`);
  await page.waitForLoadState("networkidle");
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm new password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  await expect(page.getByText(/your password has been reset/i)).toBeVisible();

  // ---- The old password no longer works; the new one does ----
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Incorrect email or password.")).toBeVisible();

  await page.getByLabel("Password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/(customers|onboarding)/);

  // ---- The session opened BEFORE the reset is genuinely dead (server-
  // side revocation, not merely a client-side token wipe) ----
  await oldSessionPage.goto("/customers");
  await oldSessionPage.waitForLoadState("networkidle");
  await expect(oldSessionPage).toHaveURL(/\/login$/);

  await oldSessionContext.close();
  await api.dispose();
});

test("reset_with_an_invalid_token_shows_the_invalid_state", async ({ page }) => {
  await page.goto("/reset-password?token=not-a-real-token");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("New password", { exact: true }).fill("some-new-password-1");
  await page.getByLabel("Confirm new password").fill("some-new-password-1");
  await page.getByRole("button", { name: "Reset password" }).click();
  await expect(page.getByText(/invalid or has expired/i)).toBeVisible();
});
