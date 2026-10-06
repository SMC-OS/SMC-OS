import { expect, test } from "@playwright/test";

test("demo stone journey is interactive, isolated and reaches handover", async ({
  page,
}) => {
  const apiRequests: string[] = [];

  page.on("request", (request) => {
    if (request.url().includes("/api/v1/")) {
      apiRequests.push(request.url());
    }
  });

  await page.goto("/demo");

  await expect(
    page.getByRole("heading", { name: "Demo Workspace" }),
  ).toBeVisible();

  await expect(page.getByText(/entirely synthetic/i)).toBeVisible();

  await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Customers" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Account/ })).toHaveCount(0);

  await page.getByRole("button", { name: "Create demo customer" }).click();

  await expect(
    page.getByText(/Customer: GeoCore Demo Customer/),
  ).toBeVisible();

  await page.getByRole("button", { name: "Create stone quote" }).click();

  await expect(page.getByText(/DEMO-S-001/)).toBeVisible();

  await page.getByRole("button", { name: "Send quote (simulated)" }).click();
  await page.getByRole("button", { name: "Approve quote" }).click();
  await page.getByRole("button", { name: "Convert to project" }).click();
  await page.getByRole("button", { name: "Complete handover" }).click();

  await expect(page.getByText("Handover complete ✓")).toBeVisible();

  await page.getByRole("tab", { name: "Projects" }).click();
  await expect(page.getByText("Quartz worktop - Demo")).toBeVisible();

  await page.getByRole("button", { name: "Reset demo workspace" }).click();

  await expect(
    page.getByRole("button", { name: "Create demo customer" }),
  ).toBeVisible();

  expect(apiRequests).toEqual([]);
});

test("demo construction, AI, email and invite actions remain synthetic", async ({
  page,
}) => {
  const apiRequests: string[] = [];

  page.on("request", (request) => {
    if (request.url().includes("/api/v1/")) {
      apiRequests.push(request.url());
    }
  });

  await page.goto("/demo");

  await page.getByRole("button", { name: "Create demo customer" }).click();

  await page
    .getByRole("button", { name: "Create construction quote" })
    .click();

  await expect(page.getByText(/DEMO-C-001/)).toBeVisible();

  await page.getByRole("button", { name: "Send quote (simulated)" }).click();
  await page.getByRole("button", { name: "Approve quote" }).click();
  await page.getByRole("button", { name: "Convert to project" }).click();

  await page.getByRole("tab", { name: "Projects" }).click();
  await expect(page.getByText("Rear extension - Demo")).toBeVisible();

  await page.getByRole("tab", { name: "GeoCore AI" }).click();

  await page
    .getByRole("button", {
      name: "Ask GeoCore AI to prepare quote follow-up",
    })
    .click();

  await expect(
    page.getByText(
      "Prepared a follow-up task for DEMO-C-001. Demo only - nothing was sent or saved.",
    ),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Communications" }).click();

  await page
    .getByRole("button", { name: "Simulate customer email" })
    .click();

  await expect(
    page.getByText("Demo only - no real email was delivered."),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Settings" }).click();

  await page
    .getByRole("button", { name: "Simulate team invite" })
    .click();

  await expect(
    page.getByText("Demo only - no invitation was delivered."),
  ).toBeVisible();

  await expect(
    page.getByRole("button", { name: "Billing unavailable in demo" }),
  ).toBeDisabled();

  expect(apiRequests).toEqual([]);
});
