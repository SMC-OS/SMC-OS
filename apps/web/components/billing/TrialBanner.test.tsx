/**
 * Phase B — the in-app trial banner: shown only for GeoCore's no-card
 * trial, amber in the last 3 days, and never on /pricing or for paid
 * workspaces.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

let authState: Record<string, unknown>;
vi.mock("@/components/auth/AuthProvider", () => ({ useAuth: () => authState }));

const getSubscriptionMock = vi.fn();
vi.mock("@/lib/api", () => ({ api: { getSubscription: () => getSubscriptionMock() } }));

import { TrialBanner } from "./TrialBanner";

beforeEach(() => {
  pathname = "/";
  authState = {
    isReady: true,
    isAuthenticated: true,
    verificationRequired: false,
    billingAccessRequired: false,
    role: "Owner",
  };
  getSubscriptionMock.mockReset();
});

afterEach(cleanup);

describe("TrialBanner", () => {
  it("shows days left and a plan link for the owner during a no-card trial", async () => {
    getSubscriptionMock.mockResolvedValue({ trial_state: "active", trial_days_remaining: 9 });
    render(<TrialBanner />);
    expect(await screen.findByText("9 days left")).toBeInTheDocument();
    expect(screen.getByText(/No card required/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose a plan" })).toHaveAttribute("href", "/pricing");
  });

  it("uses the warning style in the last days and a staff-appropriate message", async () => {
    authState.role = "Staff";
    getSubscriptionMock.mockResolvedValue({ trial_state: "ending_soon", trial_days_remaining: 1 });
    render(<TrialBanner />);
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("1 day left");
    expect(banner.className).toContain("warning");
    expect(screen.queryByRole("link", { name: "Choose a plan" })).toBeNull();
  });

  it("renders nothing for a paid or grandfathered workspace", async () => {
    getSubscriptionMock.mockResolvedValue({ status: "active", trial_state: null });
    const { container } = render(<TrialBanner />);
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it("stays off /pricing, which shows the full trial state itself", async () => {
    pathname = "/pricing";
    getSubscriptionMock.mockResolvedValue({ trial_state: "active", trial_days_remaining: 9 });
    const { container } = render(<TrialBanner />);
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it("never fetches for a user still blocked by verification or billing", () => {
    authState.billingAccessRequired = true;
    render(<TrialBanner />);
    expect(getSubscriptionMock).not.toHaveBeenCalled();
  });
});
