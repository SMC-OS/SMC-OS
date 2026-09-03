/**
 * Production incident (post-v1.0.1): a 401 (expired/invalid session) was
 * shown to the user as "Couldn't reach the SIMO OS API" — indistinguishable
 * from a real network/API-availability failure. A 401/403 is an
 * authentication problem; only a true network failure or a 5xx is an
 * availability problem, and the two must read differently.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useOnlineStatus", () => ({
  useOnlineStatus: () => true,
}));

import { DashboardStatusBar } from "@/components/dashboard/DashboardStatusBar";

afterEach(() => {
  cleanup();
});

describe("DashboardStatusBar — distinguishes auth errors from API-availability errors", () => {
  it("does not claim the API is unreachable when the failure is an expired/invalid session (401)", () => {
    render(
      <DashboardStatusBar
        status="error"
        error="Request to /dashboard failed with 401"
        isAuthError={true}
      />
    );

    expect(screen.queryByText(/Couldn.t reach the SIMO OS API/i)).not.toBeInTheDocument();
    expect(screen.getByText(/session/i)).toBeInTheDocument();
  });

  it("still reports a genuine network/API-availability failure as unreachable", () => {
    render(
      <DashboardStatusBar
        status="error"
        error="Could not reach the API at /dashboard"
        isAuthError={false}
      />
    );

    expect(screen.getByText(/Couldn.t reach the SIMO OS API/i)).toBeInTheDocument();
  });

  it("still reports a 5xx as an availability failure, not a session problem", () => {
    render(
      <DashboardStatusBar
        status="error"
        error="Request to /dashboard failed with 500"
        isAuthError={false}
      />
    );

    expect(screen.getByText(/Couldn.t reach the SIMO OS API/i)).toBeInTheDocument();
  });
});
