import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Sprint 020 — first true browser E2E runner. Hardcoded to loopback URLs on
 * purpose (no env-var override): there is no way to point this suite at a
 * deployed/production origin without editing this file, which is the
 * safety property Sprint 020 requires instead of a runtime "is this prod?"
 * check.
 *
 * FRONTEND_URL must be "localhost", not "127.0.0.1": Next.js dev mode only
 * allows "localhost" for its own dev/HMR resources by default (its
 * allowedDevOrigins guard), and hitting it via 127.0.0.1 silently breaks
 * client-side JS on the page instead of raising a clear error.
 */
export const FRONTEND_URL = "http://localhost:3000";
export const BACKEND_URL = "http://127.0.0.1:8000";

const REPO_ROOT = path.resolve(__dirname, "..", "..");

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Real Next.js dev server + real FastAPI server (app.main:app, same
  // module Dockerfile's CMD boots — see repo root Dockerfile) against the
  // already-running local Postgres (docker-compose.yml). Neither the
  // frontend's fetch/router nor the backend's TestClient are mocked here.
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: REPO_ROOT,
      url: `${BACKEND_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "pnpm run dev",
      cwd: __dirname,
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
