import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getSubscription = vi.fn();
vi.mock("@/lib/api", () => ({ api: {
  getSubscription: () => getSubscription(),
  getPlans: async () => [],
} }));

import { BillingCard } from "./BillingCard";

afterEach(cleanup);

describe("BillingCard billing disclosures", () => {
  it("shows permanent free access without paid billing controls", async () => {
    getSubscription.mockResolvedValue({ plan: "pro", status: "active",
      billing_period: "monthly", complimentary: true });
    render(<BillingCard />);
    expect(await screen.findByText("Complimentary access — no recurring charge or expiry.")).toBeInTheDocument();
    expect(screen.queryByText(/Billed monthly/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Cancel plan" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Payment method & invoices" })).toBeNull();
  });

  it("keeps paid subscription controls and recurring billing disclosure", async () => {
    getSubscription.mockResolvedValue({ plan: "pro", status: "active",
      billing_period: "monthly", complimentary: false });
    render(<BillingCard />);
    expect(await screen.findByText("Billed monthly")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel plan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Payment method & invoices" })).toBeInTheDocument();
  });
});
