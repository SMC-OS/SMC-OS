import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DemoPage from "./page";

afterEach(cleanup);

describe("Demo Workspace", () => {
  it("shows_an_isolated_synthetic_construction_workspace", () => {
    render(<DemoPage />);

    expect(screen.getByRole("heading", { name: "Demo Workspace" })).toBeInTheDocument();
    expect(screen.getByText(/entirely synthetic/i)).toBeInTheDocument();
    expect(screen.getByText("Kitchen renovation — Richmond")).toBeInTheDocument();
    expect(screen.getByText("Bathroom renovation — Clapham")).toBeInTheDocument();
    expect(screen.getByText("Rear extension & refurbishment")).toBeInTheDocument();
    expect(screen.getByText("Quartz worktop — Islington")).toBeInTheDocument();
  });

  it("allows_safe_local_navigation_and_reset_without_network_or_storage", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    render(<DemoPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Quotes" }));
    expect(screen.getByText("Q-1048")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mark demo task complete" }));
    expect(screen.getByText("Demo task complete")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset demo workspace" }));
    expect(screen.getByText("Demo task ready")).toBeInTheDocument();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(storageSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
    storageSpy.mockRestore();
  });

  it("disables_external_destructive_and_ai_actions_truthfully", () => {
    render(<DemoPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Settings" }));
    expect(screen.getByRole("button", { name: "Send email unavailable in demo" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Invite unavailable in demo" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Billing unavailable in demo" })).toBeDisabled();
    expect(screen.getByText(/AI is temporarily unavailable/i)).toBeInTheDocument();
  });
});
