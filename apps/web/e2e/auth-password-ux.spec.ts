import { expect, test } from "@playwright/test";

import { grantBillingAccess } from "./billing-helper";
import { markVerified } from "./verify-helper";
test("Create Workspace password confirmation and independent visibility", async ({ page }) => {
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const password = `Demo-safe-password-${runId}`;
  const email = `password-ux-${runId}@example.invalid`;

  await page.goto("/signup");
  await page.getByLabel("Company name").fill(`Password UX ${runId}`);
  await page.getByLabel("Your name").fill("Acceptance Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill("different-password");

  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password" }).first().click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await expect(page.getByLabel("Confirm password")).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Hide password" }).click();

  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Passwords do not match.")).toBeVisible();
  await page.getByLabel("Confirm password").fill(password);
  await page.getByLabel("Confirm password").press("Enter");

  // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — a
  // brand-new signup now lands on /verify-email, not /onboarding. This
  // test's subject is the password confirmation UX, not verification —
  // the signup decision to redirect here was already made from the
  // (necessarily unverified) signup response, so verifying now and doing
  // a fresh navigation (re-fetching /auth/me on mount) is what actually
  // unlocks /onboarding, not marking verified before the click.
  await expect(page).toHaveURL(/\/verify-email$/);
  markVerified(email);
  grantBillingAccess(email);
  await page.goto("/onboarding");
  await expect(page).toHaveURL(/\/onboarding$/);
});

test("Login password can be shown and hidden before Enter submits", async ({ page, request }) => {
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const email = `login-password-ux-${runId}@example.invalid`;
  const password = `Login-safe-password-${runId}`;
  const signup = await request.post("http://127.0.0.1:8000/api/v1/auth/signup", {
    data: { company_name: `Login UX ${runId}`, name: "Login Owner", email, password },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(email);
  grantBillingAccess(email);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password")).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide password" }).click();
  await expect(page.getByLabel("Password")).toHaveAttribute("type", "password");
  await page.getByLabel("Password").press("Enter");
  await expect(page).toHaveURL(/\/customers$/);
});

// bcrypt accepts at most 72 UTF-8 bytes. 39 characters of "é" are 74
// bytes: the form must refuse it with a clear message (it used to reach
// the API and fail with a 500), and the API must answer 422 / 401.
test("An over-72-byte password is refused cleanly on signup and login", async ({ page, request }) => {
  const runId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const tooLong = "Aa1!" + "é".repeat(35);

  await page.goto("/signup");
  await page.getByLabel("Company name").fill(`Byte Limit ${runId}`);
  await page.getByLabel("Your name").fill("Byte Limit Owner");
  await page.getByLabel("Email").fill(`byte-limit-${runId}@example.invalid`);
  await page.getByLabel("Password", { exact: true }).fill(tooLong);
  await page.getByLabel("Confirm password").fill(tooLong);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("Password must be at most 72 bytes long.")).toBeVisible();
  await expect(page).toHaveURL(/\/signup/);

  const api = "http://127.0.0.1:8000/api/v1/auth";
  const signup = await request.post(`${api}/signup`, {
    data: {
      company_name: `Byte Limit API ${runId}`,
      name: "Byte Limit",
      email: `byte-limit-api-${runId}@example.invalid`,
      password: tooLong,
    },
  });
  expect(signup.status()).toBe(422);
  expect(await signup.text()).not.toContain(tooLong);

  const login = await request.post(`${api}/login`, {
    data: { email: `byte-limit-api-${runId}@example.invalid`, password: tooLong },
  });
  expect(login.status()).toBe(401);
});
