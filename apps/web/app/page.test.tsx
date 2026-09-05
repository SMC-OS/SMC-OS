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
// Sprint 036 — the Dashboard V2 panels. Each fetches on mount, so they
// are stubbed for the same reason the Sprint 028 panels above are: this
// file is about the greeting and the auth guard, not about data loading.
vi.mock("@/components/dashboard/AttentionPanel", () => ({
  AttentionPanel: () => null,
}));
vi.mock("@/components/dashboard/UpcomingPanel", () => ({
  UpcomingPanel: () => null,
}));
vi.mock("@/components/dashboard/AutomationActivityPanel", () => ({
  AutomationActivityPanel: () => null,
}));
vi.mock("@/components/dashboard/AIInsightCard", () => ({
  AIInsightCard: () => null,
}));
vi.mock("@/components/workspace/WorkspaceProvider", () => ({
  useWorkspace: () => ({ profile: null, currency: "GBP", loading: false, refresh: () => {} }),
}));
vi.mock("@/hooks/useDashboardStats", () => ({
  useDashboardStats: () => ({ status: "success", error: null, isAuthError: false, data: null }),
}));

let mockAuth: {
  name: string | null;
  tenantName?: string | null;
  isAuthenticated: boolean;
  isReady: boolean;
};

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => mockAuth,
}));

import DashboardPage from "./page";

afterEach(() => {
  cleanup();
  replaceMock.mockClear();
});

describe("DashboardPage — Sprint 028 UAT-003", () => {
  // Sprint 036 rewrote the greeting: it is now time-of-day based and uses
  // the signed-in user's first name ("Good morning, Jordan") instead of a
  // fixed "Welcome back, <full name>". The defect this test exists to
  // catch is unchanged and is still asserted — the greeting must come
  // from the real signed-in user and must never be a hardcoded name — so
  // the assertion matches the name rather than the surrounding wording.
  it("greets_the_actual_signed_in_user_by_their_real_name_not_a_placeholder", () => {
    mockAuth = { name: "Jordan Staff", isAuthenticated: true, isReady: true };

    render(<DashboardPage />);

    expect(
      screen.getByRole("heading", { name: /jordan/i, level: 1 })
    ).toBeInTheDocument();
    expect(screen.queryByText(/simo/i)).not.toBeInTheDocument();
  });

  it("greets_without_a_name_rather_than_inventing_one_when_the_user_has_none", () => {
    mockAuth = { name: null, isAuthenticated: true, isReady: true };

    render(<DashboardPage />);

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toMatch(/^Good (morning|afternoon|evening)$/);
  });
});

describe("DashboardPage — production incident: redirect on an invalid/expired session", () => {
  it("redirects_to_login_once_not_authenticated_instead_of_rendering_a_broken_shell", () => {
    mockAuth = { name: null, isAuthenticated: false, isReady: true };

    render(<DashboardPage />);

    expect(replaceMock).toHaveBeenCalledWith("/login");
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  });

  it("renders nothing yet while the initial auth check is still in flight", () => {
    mockAuth = { name: null, isAuthenticated: false, isReady: false };

    render(<DashboardPage />);

    expect(replaceMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/welcome back/i)).not.toBeInTheDocument();
  });
});
