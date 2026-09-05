/**
 * Sprint 035 — GeoCore brand asset integration. The sidebar previously
 * rendered a hardcoded "S" placeholder mark (never replaced when the
 * platform was renamed SIMO OS -> GeoCore in Sprint 034, since the
 * approved brand files hadn't been supplied yet). This locks in the real
 * monogram asset and the approved tagline.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("./SidebarContext", () => ({
  useSidebar: () => ({
    collapsed: false,
    toggleCollapsed: () => {},
    mobileOpen: false,
    setMobileOpen: () => {},
  }),
}));

import { Sidebar } from "./Sidebar";

afterEach(() => {
  cleanup();
});

describe("Sidebar — GeoCore brand mark", () => {
  it("renders the real GeoCore monogram, not a placeholder letter", () => {
    render(<Sidebar />);

    const marks = screen.getAllByAltText("GeoCore");
    expect(marks.length).toBeGreaterThan(0);
    expect(marks[0].tagName).toBe("IMG");
    expect(screen.queryByText("S")).not.toBeInTheDocument();
  });

  it("shows the approved tagline, not a generic descriptor", () => {
    render(<Sidebar />);

    expect(screen.getAllByText("Build smarter together").length).toBeGreaterThan(0);
    expect(screen.queryByText("AI Operating System")).not.toBeInTheDocument();
  });
});
