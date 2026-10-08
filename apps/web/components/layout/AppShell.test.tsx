/**
 * Pre-traffic repair — public/auth shell boundary.
 *
 * A logged-out visitor on a public or auth-lifecycle route must never see
 * authenticated tenant chrome (Sidebar, Topbar, MobileNav, trial/billing
 * banner): those surfaces advertise routes the visitor has no session for
 * and dead-end at a login wall. The chrome components are mocked here so
 * this test pins the AppShell routing decision itself, not the internals
 * of any one piece of chrome.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let currentPathname = "/";
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
  useRouter: () => ({ replace: replaceMock }),
}));

let authState = {
  isReady: true,
  isAuthenticated: false,
  verificationRequired: false,
  billingAccessRequired: false,
};

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => authState,
}));

vi.mock("./Sidebar", () => ({
  Sidebar: () => <nav data-testid="sidebar" />,
}));
vi.mock("./Topbar", () => ({
  Topbar: () => <header data-testid="topbar" />,
}));
vi.mock("./MobileNav", () => ({
  MobileNav: () => <nav data-testid="mobile-nav" />,
}));
vi.mock("@/components/billing/TrialBanner", () => ({
  TrialBanner: () => <div data-testid="trial-banner" />,
}));

import AppShell from "./AppShell";

const PUBLIC_ROUTES = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/invite",
  "/invite/some-invite-token",
  "/portal",
  "/portal/some-portal-token",
  "/pricing",
  "/demo",
];

beforeEach(() => {
  replaceMock.mockClear();
  authState = {
    isReady: true,
    isAuthenticated: false,
    verificationRequired: false,
    billingAccessRequired: false,
  };
});

afterEach(cleanup);

describe("AppShell public/auth boundary", () => {
  for (const route of PUBLIC_ROUTES) {
    it(`renders ${route} standalone without tenant chrome`, () => {
      currentPathname = route;
      render(
        <AppShell>
          <div data-testid="page-content" />
        </AppShell>,
      );

      expect(screen.getByTestId("page-content")).toBeInTheDocument();
      expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
      expect(screen.queryByTestId("topbar")).not.toBeInTheDocument();
      expect(screen.queryByTestId("mobile-nav")).not.toBeInTheDocument();
      expect(screen.queryByTestId("trial-banner")).not.toBeInTheDocument();
    });
  }

  it("renders the full tenant shell on an authenticated protected route", () => {
    currentPathname = "/customers";
    authState = { ...authState, isAuthenticated: true };
    render(
      <AppShell>
        <div data-testid="page-content" />
      </AppShell>,
    );

    expect(screen.getByTestId("page-content")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("topbar")).toBeInTheDocument();
    expect(screen.getByTestId("mobile-nav")).toBeInTheDocument();
    expect(screen.getByTestId("trial-banner")).toBeInTheDocument();
  });

  it("never renders tenant chrome for a logged-out protected route", () => {
    currentPathname = "/customers";

    render(
      <AppShell>
        <div data-testid="page-content" />
      </AppShell>,
    );

    expect(screen.queryByTestId("sidebar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("topbar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mobile-nav")).not.toBeInTheDocument();
    expect(screen.queryByTestId("trial-banner")).not.toBeInTheDocument();
  });
});
