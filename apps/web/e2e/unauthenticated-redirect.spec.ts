import { expect, test } from "@playwright/test";

/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.10/§8) — every staff-only
 * frontend route redirects an unauthenticated visitor to /login. No prior
 * Playwright spec ever visited these routes with no token present — every
 * existing spec signs up first. No API setup needed here at all: the
 * point is proving the *frontend's own* client-side guard
 * (docs/USER_ROLES.md §1: a client-side check-on-mount, not
 * Next.js middleware/SSR-level), independent of any backend call.
 */

const PROTECTED_ROUTES = ["/customers", "/projects", "/quotes", "/settings"];

test("every_staff_only_route_redirects_to_login_with_no_token_present", async ({ page }) => {
  for (const route of PROTECTED_ROUTES) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/login$/, {
      timeout: 10_000,
    });
  }
});
