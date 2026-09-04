/**
 * Sprint 032 (Workstream A) — pricing page: annual-recommended messaging,
 * Pro/Business/Enterprise rendering, and checkout initiation.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PricingPage from "./page";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

let authState: { isAuthenticated: boolean; role: string | null };
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => authState,
}));

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

const PLANS = [
  {
    plan: "pro",
    name: "GeoCore Pro",
    self_service: true,
    monthly_price_gbp: 79,
    annual_price_gbp: 790,
    annual_recommended: true,
    entitlements: { seats: 5, ai_usage_per_month: 500, automations: 10, integrations: 3, advanced_analytics: false },
  },
  {
    plan: "business",
    name: "GeoCore Business",
    self_service: true,
    monthly_price_gbp: 149,
    annual_price_gbp: 1490,
    annual_recommended: true,
    entitlements: { seats: 25, ai_usage_per_month: 5000, automations: 100, integrations: 15, advanced_analytics: true },
  },
  {
    plan: "enterprise",
    name: "Enterprise",
    self_service: false,
    monthly_price_gbp: null,
    annual_price_gbp: null,
    annual_recommended: false,
    entitlements: { seats: null, ai_usage_per_month: null, automations: null, integrations: null, advanced_analytics: true },
  },
];

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  authState = { isAuthenticated: true, role: "Owner" };
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/billing/plans")) return jsonResponse(PLANS);
    if (url.endsWith("/billing/checkout") && init?.method === "POST") {
      return jsonResponse({ checkout_url: "https://checkout.stripe.com/pay/cs_fake" });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PricingPage", () => {
  it("shows all three plans with annual savings messaging", async () => {
    render(<PricingPage />);

    expect(await screen.findByText("GeoCore Pro")).toBeInTheDocument();
    expect(screen.getByText("GeoCore Business")).toBeInTheDocument();
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
    expect(screen.getAllByText(/save 2 months/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("starts checkout for the selected plan and redirects to the hosted Stripe URL", async () => {
    const assignMock = vi.fn();
    const originalLocation = window.location;
    // @ts-expect-error -- test override of a readonly global
    delete window.location;
    // @ts-expect-error -- reassigning for assertion
    window.location = { ...originalLocation, assign: assignMock };

    render(<PricingPage />);

    const proButton = await screen.findByRole("button", { name: /choose geocore pro/i });
    await userEvent.click(proButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/billing/checkout"),
        expect.objectContaining({ method: "POST" })
      );
    });

    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/billing/checkout"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.plan).toBe("pro");
    expect(body.billing_period).toBe("annual");

    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith("https://checkout.stripe.com/pay/cs_fake");
    });

    // @ts-expect-error -- restoring the global
    window.location = originalLocation;
  });

  it("prompts sign-in instead of checkout for an unauthenticated visitor", async () => {
    authState = { isAuthenticated: false, role: null };
    render(<PricingPage />);

    expect(await screen.findAllByRole("button", { name: /sign in to subscribe/i })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /choose geocore pro/i })).not.toBeInTheDocument();
  });

  it("tells a Staff user to ask their owner instead of offering checkout", async () => {
    authState = { isAuthenticated: true, role: "Staff" };
    render(<PricingPage />);

    expect(await screen.findAllByText(/ask your workspace owner/i)).toHaveLength(2);
  });
});
