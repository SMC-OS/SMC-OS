/**
 * Sprint 032 (Workstream A) — pricing page: annual-recommended messaging,
 * plan rendering, and checkout initiation. Widened to the locked 4-tier
 * catalogue (Starter/Team/Pro/Business/Enterprise) in Sprint 039
 * Production Readiness Defect Gate, Blocker 3 — do not restore the old
 * 2-tier Pro/Business-only fixture.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PricingPage from "./page";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

let authState: {
  isAuthenticated: boolean;
  role: string | null;
  billingAccessRequired?: boolean;
  refreshAccess?: () => Promise<unknown>;
};
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => authState,
}));

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

const PLANS = [
  {
    plan: "starter",
    name: "GeoCore Starter",
    self_service: true,
    monthly_price_gbp: 29,
    annual_price_gbp: 290,
    annual_recommended: true,
    entitlements: { seats: 1, ai_usage_per_month: 100, automations: 5, integrations: 1, advanced_analytics: false },
  },
  {
    plan: "team",
    name: "GeoCore Team",
    self_service: true,
    monthly_price_gbp: 59,
    annual_price_gbp: 590,
    annual_recommended: true,
    entitlements: { seats: 3, ai_usage_per_month: 500, automations: 20, integrations: 3, advanced_analytics: false },
  },
  {
    plan: "pro",
    name: "GeoCore Pro",
    self_service: true,
    monthly_price_gbp: 99,
    annual_price_gbp: 990,
    annual_recommended: true,
    entitlements: { seats: 10, ai_usage_per_month: 2000, automations: 75, integrations: 10, advanced_analytics: true },
  },
  {
    plan: "business",
    name: "GeoCore Business",
    self_service: true,
    monthly_price_gbp: 199,
    annual_price_gbp: 1990,
    annual_recommended: true,
    entitlements: { seats: 25, ai_usage_per_month: 5000, automations: 150, integrations: 15, advanced_analytics: true },
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
let subscriptionResponse: unknown = null;

beforeEach(() => {
  authState = { isAuthenticated: true, role: "Owner" };
  subscriptionResponse = null;
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/billing/plans")) return jsonResponse(PLANS);
    if (url.endsWith("/billing/subscription")) return jsonResponse(subscriptionResponse);
    if (url.endsWith("/billing/trial") && init?.method === "POST") {
      return jsonResponse({ ...(PLANS[2] as object), status: "trialing", trial_state: "active" }, 201);
    }
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
  it("shows all five plans with annual savings messaging", async () => {
    render(<PricingPage />);

    expect(await screen.findByText("GeoCore Starter")).toBeInTheDocument();
    expect(screen.getByText("GeoCore Team")).toBeInTheDocument();
    expect(screen.getByText("GeoCore Pro")).toBeInTheDocument();
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

    expect(await screen.findAllByRole("button", { name: /sign in to subscribe/i })).toHaveLength(4);
    expect(screen.queryByRole("button", { name: /choose geocore pro/i })).not.toBeInTheDocument();
  });

  it("tells a Staff user to ask their owner instead of offering checkout", async () => {
    authState = { isAuthenticated: true, role: "Staff" };
    render(<PricingPage />);

    expect(await screen.findAllByText(/ask your workspace owner/i)).toHaveLength(4);
  });

  it("shows the trial countdown and marks the trialing plan as current", async () => {
    subscriptionResponse = {
      id: "sub-1",
      tenant_id: "tenant-1",
      plan: "pro",
      billing_period: "monthly",
      status: "trialing",
      current_period_end: null,
      cancel_at_period_end: false,
      trial_start: new Date().toISOString(),
      trial_end: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    render(<PricingPage />);

    expect(await screen.findByText(/days left in your trial/i)).toBeInTheDocument();
    expect(screen.getByText("Your trial")).toBeInTheDocument();
    // The trialing plan's own card is disabled ("Trialing this plan"),
    // not offered as something to "upgrade to" — every *other*
    // self-service plan gets the upgrade CTA instead.
    expect(screen.getByRole("button", { name: /trialing this plan/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upgrade to geocore business/i })).toBeInTheDocument();
  });

  describe("Phase B — no-card trial states", () => {
    it("never says a card is required", async () => {
      authState = { isAuthenticated: true, role: "Owner" };
      render(<PricingPage />);
      expect(await screen.findByText(/No card required/)).toBeInTheDocument();
      expect(screen.queryByText(/card is required/i)).toBeNull();
    });

    it("shows days left, keeps the chosen billing period and offers to subscribe to the trial plan", async () => {
      authState = { isAuthenticated: true, role: "Owner" };
      subscriptionResponse = {
      id: "sub-1",
      tenant_id: "tenant-1",
      plan: "team",
      billing_period: "monthly",
      status: "trialing",
      current_period_end: null,
      cancel_at_period_end: false,
      trial_start: new Date().toISOString(),
      trial_end: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      trial_state: "ending_soon",
      trial_days_remaining: 2,
    };
      render(<PricingPage />);

      expect(await screen.findByText("2 days left in your free trial")).toBeInTheDocument();
      expect(screen.getByText(/won't be charged until your trial ends/i)).toBeInTheDocument();
      // The period chosen at signup (monthly) replaces the page's annual
      // default, so monthly prices show.
      expect(await screen.findAllByText("/mo")).not.toHaveLength(0);
      expect(screen.queryAllByText("/yr")).toHaveLength(0);
      expect(screen.getByRole("button", { name: "Subscribe to GeoCore Team" })).toBeEnabled();
    });

    it("explains an expired trial without implying data loss", async () => {
      authState = { isAuthenticated: true, role: "Owner", billingAccessRequired: true };
      subscriptionResponse = {
      id: "sub-1",
      tenant_id: "tenant-1",
      plan: "team",
      billing_period: "annual",
      status: "trialing",
      current_period_end: null,
      cancel_at_period_end: false,
      trial_start: new Date().toISOString(),
      trial_end: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      trial_state: "expired",
      trial_days_remaining: 0,
    };
      render(<PricingPage />);

      expect(await screen.findByText("Your 14-day free trial has ended.")).toBeInTheDocument();
      expect(screen.getByText(/nothing has been deleted/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /start free trial/i })).toBeNull();
    });

    it("lets an owner with no subscription start the free trial without a card", async () => {
      const refreshAccess = vi.fn().mockResolvedValue({ verificationRequired: false, billingAccessRequired: false });
      authState = { isAuthenticated: true, role: "Owner", billingAccessRequired: true, refreshAccess };
      subscriptionResponse = null;
      render(<PricingPage />);

      const start = await screen.findByRole("button", { name: "Start free trial" });
      await userEvent.click(start);

      await waitFor(() => expect(refreshAccess).toHaveBeenCalled());
      expect(pushMock).toHaveBeenCalledWith("/onboarding");
      const trialCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/billing/trial"));
      expect(trialCall?.[1]?.method).toBe("POST");
    });

    it("never offers a trial to staff", async () => {
      authState = { isAuthenticated: true, role: "Staff", billingAccessRequired: true };
      subscriptionResponse = null;
      render(<PricingPage />);
      await screen.findAllByText(/ask your workspace owner/i);
      expect(screen.queryByRole("button", { name: "Start free trial" })).toBeNull();
    });
  });
});
