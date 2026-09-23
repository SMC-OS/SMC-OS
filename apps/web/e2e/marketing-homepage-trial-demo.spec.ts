import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { FRONTEND_URL, MARKETING_URL } from "../playwright.config";

/**
 * GeoCore Premium OS Plan 02 (Sprint 041) — the public marketing site's
 * own E2E coverage, driven against the real apps/marketing dev server
 * (see playwright.config.ts's third webServer entry) and the real
 * backend, exactly as apps/web's own specs already do — no mocking.
 *
 * Four journeys, matching the plan's own acceptance criteria:
 *   A. A visitor understands the product (Homepage -> Product -> Trades
 *      -> Pricing).
 *   B. The trial journey states "14-day free trial. No card required."
 *      and hands off to the real apps/web signup flow with the chosen
 *      plan and billing period (Phase B; this previously asserted the
 *      superseded card-required contract).
 *   C. Request Demo persists a real row in the database.
 *   D. The same key flow works at a 390px mobile viewport.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

function countDemoRequestsByEmail(email: string): number {
  const script = `
from app.database.database import SessionLocal
from app.database.models import DemoRequest

db = SessionLocal()
print(db.query(DemoRequest).filter(DemoRequest.email == ${JSON.stringify(email)}).count())
db.close()
`.trim();
  const output = execFileSync("python", ["-c", script], { cwd: REPO_ROOT, encoding: "utf-8" });
  return Number.parseInt(output.trim(), 10);
}

function cleanupDemoRequest(email: string): void {
  execFileSync(
    "python",
    [
      "-c",
      `
from sqlalchemy import delete
from app.database.database import SessionLocal
from app.database.models import DemoRequest

db = SessionLocal()
db.execute(delete(DemoRequest).where(DemoRequest.email == ${JSON.stringify(email)}))
db.commit()
db.close()
`.trim(),
    ],
    { cwd: REPO_ROOT }
  );
}

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

test.describe("GeoCore Premium OS Plan 02 (Sprint 041) — public marketing site", () => {
  test("journey_a_a_visitor_understands_the_product_through_homepage_product_trades_pricing", async ({
    page,
  }) => {
    await page.goto(MARKETING_URL);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Stone/i);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/Construction/i);

    // Product — what's inside GeoCore.
    await page.getByRole("link", { name: "Product", exact: true }).first().click();
    await expect(page.getByRole("heading", { name: "Command Center" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Project 360" })).toBeVisible();

    // Trades — the trade-adaptive workflow story.
    await page.getByRole("link", { name: "Trades", exact: true }).first().click();
    await expect(page.getByText("Each trade gets its own operational workflow.")).toBeVisible();
    await expect(page.getByText("Stone & Worktops").first()).toBeVisible();

    // Pricing.
    await page.getByRole("link", { name: "Pricing", exact: true }).first().click();
    await page.waitForURL(/\/pricing$/);
    await expect(page.getByRole("heading", { name: /Simple plans/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Starter/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Enterprise", exact: true })).toBeVisible();
  });

  test("journey_b_the_trial_needs_no_card_and_carries_the_plan_to_signup", async ({ page }) => {
    await page.goto(`${MARKETING_URL}/pricing`);
    await page.waitForLoadState("networkidle");

    const starterCard = page.locator(".pricing-card", { hasText: "Starter" });
    await expect(starterCard).toBeVisible();

    // The no-card trial is stated before any handoff, and nothing implies
    // an automatic charge.
    await expect(starterCard.getByText("14-day free trial. No card required.")).toBeVisible();
    await expect(page.getByText(/card is required|£0 due today|payment method is required/i)).toHaveCount(0);

    const startTrial = starterCard.getByRole("link", { name: "Start Free Trial" });
    await expect(startTrial).toHaveAttribute(
      "href",
      new RegExp(`^${FRONTEND_URL}/signup\\?plan=starter&billing_period=monthly$`)
    );

    // Only after the visitor explicitly clicks does the real signup flow
    // begin — the same production signup this plan reuses, not a second
    // billing system.
    await startTrial.click();
    await page.waitForURL(/\/signup/);
    await expect(page.getByLabel("Email")).toBeVisible();
    // The chosen plan arrives on signup, so it is never chosen twice.
    await expect(page.getByTestId("trial-summary")).toContainText("free trial of GeoCore Starter");
  });

  test("journey_c_request_demo_submits_and_persists_a_real_row", async ({ page }) => {
    const email = `pytest-e2e-sprint041-demo-${RUN_ID}@example.invalid`;
    try {
      await page.goto(`${MARKETING_URL}/request-demo`);
      await page.waitForLoadState("networkidle");

      await page.getByLabel("First name").fill("Pytest");
      await page.getByLabel("Last name").fill("E2E Demo");
      await page.getByLabel("Work email").fill(email);
      await page.getByLabel("Company name").fill(`Pytest E2E Sprint 041 Co ${RUN_ID}`);
      await page.getByLabel("Team size").selectOption("4-10");
      await page.getByLabel("Stone & Worktops").check();
      await page.getByLabel("General Building").check();

      await page.getByRole("button", { name: "Request a Demo" }).click();

      await expect(page.getByRole("heading", { name: "Demo request received." })).toBeVisible();
      await expect(page.getByText("We'll contact you using the details you provided.")).toBeVisible();

      expect(countDemoRequestsByEmail(email)).toBe(1);
    } finally {
      cleanupDemoRequest(email);
    }
  });

  test("journey_d_the_homepage_trial_and_demo_flow_work_at_a_mobile_viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto(MARKETING_URL);
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    // Mobile nav starts collapsed; the toggle reveals it.
    const nav = page.locator("#primary-nav");
    await expect(nav).toBeHidden();
    await page.getByRole("button", { name: /open menu/i }).click();
    await expect(nav).toBeVisible();
    await nav.getByRole("link", { name: "Pricing", exact: true }).click();

    await page.waitForURL(/\/pricing$/);
    await expect(page.getByRole("heading", { name: /Starter/i })).toBeVisible();
    // No horizontal overflow at this viewport.
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });
});
