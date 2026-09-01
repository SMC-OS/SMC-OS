/**
 * Sprint 028 UAT-003 — same defect class as UAT-001
 * (components/shell/UserProfileMenu.test.tsx): the dashboard's own
 * greeting hardcodes "Welcome back, Simo" regardless of who is actually
 * signed in. AuthProvider already exposes the real `name` (added for
 * UAT-001) but this page never consumed it.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  useDashboardStats: () => ({ status: "success", error: null, data: null }),
}));

let mockAuth: { name: string | null };

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => mockAuth,
}));

import DashboardPage from "./page";

afterEach(() => {
  cleanup();
});

describe("DashboardPage — Sprint 028 UAT-003", () => {
  it("greets_the_actual_signed_in_user_by_their_real_name_not_a_placeholder", () => {
    mockAuth = { name: "Jordan Staff" };

    render(<DashboardPage />);

    expect(screen.getByText("Welcome back, Jordan Staff")).toBeInTheDocument();
    expect(screen.queryByText("Welcome back, Simo")).not.toBeInTheDocument();
  });
});
