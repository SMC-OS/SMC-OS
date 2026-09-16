import { execFileSync } from "node:child_process";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { BACKEND_URL } from "../playwright.config";
import { markVerified } from "./verify-helper";

/**
 * Sprint 027 (docs/SPRINTS/sprint-027.md §6.13/§8) — tests/test_portal.py
 * proves revoked/expired portal-token behavior thoroughly at the API
 * layer (test_revoked_portal_link_reads_as_revoked_and_returns_no_data,
 * test_expired_portal_link_reads_as_expired_and_returns_no_data), but no
 * prior Playwright spec ever opened /portal/[token] in a browser for
 * either state — every existing spec only covers a currently-active link.
 *
 * No HTTP path exists (by design) to backdate a link's expires_at, so —
 * matching e2e/follow-up-automation.spec.ts's own precedent of shelling
 * out to a real backend entrypoint rather than adding a test-only HTTP
 * route — this spec runs a small, verification-only inline script
 * against the same database the running FastAPI server uses.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUN_ID = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const COMPANY_NAME = `Pytest E2E Sprint 027 Portal Lifecycle Co ${RUN_ID}`;
const OWNER_EMAIL = `pytest-e2e-sprint027-portal-owner-${RUN_ID}@example.invalid`;
const OWNER_PASSWORD = `Pytest-E2e-Sprint027-Portal-Owner-Password-${RUN_ID}!`;
const CUSTOMER_NAME = `Pytest E2E Sprint 027 Portal Lifecycle Customer ${RUN_ID}`;

function backdatePortalLinkExpiry(portalLinkId: string): void {
  execFileSync(
    "python",
    [
      "-c",
      "import sys, uuid\n" +
        "from datetime import datetime, timedelta, timezone\n" +
        "from app.database.database import SessionLocal\n" +
        "from app.database.models import PortalLink\n" +
        "portal_link_id = uuid.UUID(sys.argv[1])\n" +
        "with SessionLocal() as db:\n" +
        "    row = db.get(PortalLink, portal_link_id)\n" +
        "    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)\n" +
        "    db.commit()\n",
      portalLinkId,
    ],
    { cwd: REPO_ROOT, encoding: "utf-8" }
  );
}

test("an_expired_portal_link_shows_a_clear_no_longer_valid_state", async ({ page }) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `${COMPANY_NAME} Expired`,
      name: "Pytest E2E Owner",
      email: `expired-${OWNER_EMAIL}`,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(`expired-${OWNER_EMAIL}`);
  const { access_token: ownerToken } = await signup.json();
  const ownerHeaders = { Authorization: `Bearer ${ownerToken}` };

  const customerRes = await api.post("/api/v1/customers", {
    headers: ownerHeaders,
    data: { name: `${CUSTOMER_NAME} Expired` },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customerId = (await customerRes.json()).id as string;

  const linkRes = await api.post("/api/v1/portal-links", {
    headers: ownerHeaders,
    data: { customer_id: customerId },
  });
  expect(linkRes.ok()).toBeTruthy();
  const link = await linkRes.json();

  backdatePortalLinkExpiry(link.id);

  await page.goto(`/portal/${link.token}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(/This link has expired/)).toBeVisible();

  await api.dispose();
});

test("a_revoked_portal_link_shows_a_clear_no_longer_valid_state", async ({ page }) => {
  const api = await request.newContext({ baseURL: BACKEND_URL });

  const signup = await api.post("/api/v1/auth/signup", {
    data: {
      company_name: `${COMPANY_NAME} Revoked`,
      name: "Pytest E2E Owner",
      email: `revoked-${OWNER_EMAIL}`,
      password: OWNER_PASSWORD,
    },
  });
  expect(signup.ok()).toBeTruthy();
  markVerified(`revoked-${OWNER_EMAIL}`);
  const { access_token: ownerToken } = await signup.json();
  const ownerHeaders = { Authorization: `Bearer ${ownerToken}` };

  const customerRes = await api.post("/api/v1/customers", {
    headers: ownerHeaders,
    data: { name: `${CUSTOMER_NAME} Revoked` },
  });
  expect(customerRes.ok()).toBeTruthy();
  const customerId = (await customerRes.json()).id as string;

  const linkRes = await api.post("/api/v1/portal-links", {
    headers: ownerHeaders,
    data: { customer_id: customerId },
  });
  expect(linkRes.ok()).toBeTruthy();
  const link = await linkRes.json();

  const revoked = await api.delete(`/api/v1/portal-links/${link.id}`, { headers: ownerHeaders });
  expect(revoked.ok()).toBeTruthy();

  await page.goto(`/portal/${link.token}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(/This link has been revoked/)).toBeVisible();

  await api.dispose();
});
