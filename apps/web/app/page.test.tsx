/**
 * Sprint 028 UAT-003 — same defect class as UAT-001
 * (components/shell/UserProfileMenu.test.tsx): the dashboard's own
 * greeting hardcodes "Welcome back, Simo" regardless of who is actually
 * signed in. AuthProvider already exposes the real `name` (added for
 * UAT-001) but this page never consumed it.
 *
 * Production incident (post-v1.0.1): every other protected page
 * (customers, projects, quotes, settings) redirects to /login once
 * AuthProvider's isAuthenticated flips false — the dashboard never did.
 * Combined with AuthProvider not reacting to a token expiring mid-session,
 * a signed-out user was left staring at a broken dashboard shell instead
 * of being sent to /login.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Same reasoning as app/settings/page.test.tsx: a mock that returns a new
// function every render would re-fire any effect depending on `router`.
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("@/components/dashboard/command-centre/CommandCentrePanel", () => ({
  CommandCentrePanel: () => null,
}));
vi.mock("@/components/dashboard/DashboardStatusBar", () => ({
  DashboardStatusBar: () => null,
}));
vi.mock("@/components/dashboard/QuickActions", () => ({
  QuickActions: () => null,
}));
vi.mock("@/components/dashboard/RecentActivityPanel", () => ({
  RecentActivityPanel: () => null,
}));
vi.mock("@/components/dashboard/StatGrid", () => ({
  StatGrid: () => null,
}));
vi.mock("@/hooks/useDashboardStats", () => ({
  useDashboardStats: () => ({ status: "success", error: null, isAuthError: false, data: null }),
}));

let mockAuth: { name: string | null; isAuthenticated: boolean; isReady: boolean };

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => mockAuth,
}));

import DashboardPage from "./page";

afterEach(() => {
  cleanup();
  replaceMock.mockClear();
});

describe("DashboardPage — Sprint 028 UAT-003", () => {
  it("greets_the_actual_signed_in_user_by_their_real_name_not_a_placeholder", () => {
    mockAuth = { name: "Jordan Staff", isAuthenticated: true, isReady: true };

    render(<DashboardPage />);

    expect(screen.getByText("Welcome back, Jordan Staff")).toBeInTheDocument();
    expect(screen.queryByText("Welcome back, Simo")).not.toBeInTheDocument();
  });
});

describe("DashboardPage — production incident: redirect on an invalid/expired session", () => {
  it("redirects_to_login_once_not_authenticated_instead_of_rendering_a_broken_shell", () => {
    mockAuth = { name: null, isAuthenticated: false, isReady: true };

    render(<DashboardPage />);

    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(screen.queryByText(/welcome back/i)).not.toBeInTheDocument();
  });

  it("renders nothing yet while the initial auth check is still in flight", () => {
    mockAuth = { name: null, isAuthenticated: false, isReady: false };

    render(<DashboardPage />);

    expect(replaceMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/welcome back/i)).not.toBeInTheDocument();
  });
});
