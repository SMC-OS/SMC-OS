import { expect, test } from "@playwright/test";

test.use({
  viewport: {
    width: 390,
    height: 844,
  },
});

test("mobile login and synthetic stone demo are traffic-ready", async ({
  page,
}) => {
  await page.goto("/login");

  await expect(
    page.getByRole("heading", { name: /sign in/i }),
  ).toBeVisible();

  await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Customers" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Account/ })).toHaveCount(0);

  await page.goto("/demo");

  await expect(
    page.getByRole("heading", { name: "Demo Workspace" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Create demo customer" }).click();

  await expect(
    page.getByText(/Customer: GeoCore Demo Customer/),
  ).toBeVisible();

  await page.getByRole("button", { name: "Create stone quote" }).click();

  await expect(page.getByText(/DEMO-S-001/)).toBeVisible();

  await expect(
    page.getByRole("button", { name: "Send quote (simulated)" }),
  ).toBeVisible();

  await expect(
    page.getByRole("button", { name: "Send quote (simulated)" }),
  ).toBeEnabled();
});
