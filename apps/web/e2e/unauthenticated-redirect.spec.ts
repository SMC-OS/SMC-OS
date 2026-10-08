import { expect, test } from "@playwright/test";

const PROTECTED_ROUTES = [
  "/",
  "/customers",
  "/projects",
  "/quotes",
  "/catalogue",
  "/calendar",
  "/automations",
  "/ai",
  "/settings",
];

const PUBLIC_ROUTES = [
  "/login",
  "/signup",
  "/forgot-password",
  "/verify-email",
  "/pricing",
  "/demo",
];

async function expectNoTenantChrome(page: import("@playwright/test").Page) {
  await expect(page.getByRole("link", { name: "Dashboard" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Customers" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Quotes" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Projects" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Account/ })).toHaveCount(0);
}

test("every staff-only route redirects to login without tenant chrome", async ({
  page,
}) => {
  for (const route of PROTECTED_ROUTES) {
    await page.goto(route);

    await expect(page).toHaveURL(/\/login$/, {
      timeout: 10_000,
    });

    await expectNoTenantChrome(page);
  }
});

test("public and auth routes never expose tenant chrome", async ({ page }) => {
  for (const route of PUBLIC_ROUTES) {
    await page.goto(route);
    await expectNoTenantChrome(page);
  }
});

test("/dashboard compatibility alias does not 404 for logged-out visitors", async ({
  page,
}) => {
  const response = await page.goto("/dashboard");

  expect(response?.status()).not.toBe(404);

  await expect(page).toHaveURL(/\/login$/, {
    timeout: 10_000,
  });

  await expectNoTenantChrome(page);
});
