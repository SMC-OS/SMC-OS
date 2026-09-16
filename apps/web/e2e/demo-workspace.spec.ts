import { expect, test } from "@playwright/test";

test("demo is isolated and blocks outbound, billing, invitation and AI actions", async ({ page }) => {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/")) apiRequests.push(request.url());
  });

  await page.goto("/demo");
  await expect(page.getByRole("heading", { name: "Demo Workspace" })).toBeVisible();
  await expect(page.getByText(/entirely synthetic/i)).toBeVisible();

  // Sprint 039 V1 — a "no account needed" visitor must never see chrome
  // that dead-ends at a login wall: no real authenticated nav, no
  // account menu.
  await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Customers" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Account/ })).toHaveCount(0);
  await page.getByRole("tab", { name: "Communications" }).click();
  await expect(page.getByText("Quote follow-up drafted (not sent)")).toBeVisible();
  await page.getByRole("tab", { name: "Settings" }).click();
  await expect(page.getByRole("button", { name: "Send email unavailable in demo" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Invite unavailable in demo" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Billing unavailable in demo" })).toBeDisabled();
  await expect(page.getByText(/AI is temporarily unavailable/i)).toBeVisible();
  expect(apiRequests).toEqual([]);
});
