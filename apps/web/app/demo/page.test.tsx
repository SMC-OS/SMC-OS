import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DemoPage from "./page";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Demo Workspace", () => {
  it("shows_an_isolated_synthetic_construction_workspace", () => {
    render(<DemoPage />);

    expect(
      screen.getByRole("heading", { name: "Demo Workspace" }),
    ).toBeInTheDocument();

    expect(screen.getByText(/entirely synthetic/i)).toBeInTheDocument();
    expect(screen.getByText("Kitchen renovation - Richmond")).toBeInTheDocument();
    expect(screen.getByText("Bathroom renovation - Clapham")).toBeInTheDocument();
    expect(screen.getByText("Rear extension & refurbishment")).toBeInTheDocument();
    expect(screen.getByText("Quartz worktop - Islington")).toBeInTheDocument();
  });

  it("allows_safe_local_navigation_and_reset_without_network_or_storage", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");

    render(<DemoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Create demo customer" }));
    fireEvent.click(screen.getByRole("button", { name: "Create stone quote" }));

    expect(screen.getByText(/Quote: DEMO-S-001/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset demo workspace" }));

    expect(
      screen.getByRole("button", { name: "Create demo customer" }),
    ).toBeInTheDocument();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it("runs_the_full_synthetic_stone_journey_to_handover", () => {
    render(<DemoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Create demo customer" }));

    expect(screen.getByText(/Customer: GeoCore Demo Customer/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Create stone quote" }));

    expect(screen.getByText(/DEMO-S-001/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Quotes" }));

    expect(screen.getByText("DEMO-S-001")).toBeInTheDocument();
    expect(screen.getByText("£4,250")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Send quote (simulated)" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve quote" }));
    fireEvent.click(screen.getByRole("button", { name: "Convert to project" }));
    fireEvent.click(screen.getByRole("button", { name: "Complete handover" }));

    expect(screen.getByText("Handover complete ✓")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Projects" }));

    expect(screen.getByText("Quartz worktop - Demo")).toBeInTheDocument();
  });

  it("runs_the_synthetic_construction_quote_to_project_journey", () => {
    render(<DemoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Create demo customer" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Create construction quote" }),
    );

    fireEvent.click(screen.getByRole("tab", { name: "Quotes" }));

    const constructionQuoteId = screen.getByText("DEMO-C-001");
    expect(constructionQuoteId).toBeInTheDocument();

    const constructionQuoteCard = constructionQuoteId.closest("div");
    expect(constructionQuoteCard).toHaveTextContent("£18,400");

    fireEvent.click(screen.getByRole("button", { name: "Send quote (simulated)" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve quote" }));
    fireEvent.click(screen.getByRole("button", { name: "Convert to project" }));

    fireEvent.click(screen.getByRole("tab", { name: "Projects" }));

    expect(screen.getByText("Rear extension - Demo")).toBeInTheDocument();
  });

  it("provides_a_safe_local_geocore_ai_simulation", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<DemoPage />);

    fireEvent.click(screen.getByRole("tab", { name: "GeoCore AI" }));

    expect(
      screen.getByRole("button", {
        name: "Ask GeoCore AI to prepare quote follow-up",
      }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("tab", { name: "Projects" }));
    fireEvent.click(screen.getByRole("button", { name: "Create demo customer" }));
    fireEvent.click(screen.getByRole("button", { name: "Create stone quote" }));

    fireEvent.click(screen.getByRole("tab", { name: "GeoCore AI" }));

    fireEvent.click(
      screen.getByRole("button", {
        name: "Ask GeoCore AI to prepare quote follow-up",
      }),
    );

    expect(
      screen.getByText(
        "Prepared a follow-up task for DEMO-S-001. Demo only - nothing was sent or saved.",
      ),
    ).toBeInTheDocument();

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("simulates_email_and_invites_but_keeps_billing_disabled", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<DemoPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Communications" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Simulate customer email" }),
    );

    expect(
      screen.getByText("Demo only - no real email was delivered."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Settings" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Simulate team invite" }),
    );

    expect(
      screen.getByText("Demo only - no invitation was delivered."),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: "Billing unavailable in demo" }),
    ).toBeDisabled();

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
