/**
 * Sprint 036 (Workstream A/M) — the phone bottom bar.
 *
 * The screenshots that prompted this sprint showed real mobile layout
 * problems, so the mobile navigation contract is tested rather than
 * assumed: five slots at most, the four highest-frequency destinations
 * plus a way into everything else, hidden from tablet up (where the rail
 * takes over), and the current page announced to assistive technology
 * rather than only coloured.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

let currentPath = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => currentPath,
}));

const setMobileOpen = vi.fn();
vi.mock("./SidebarContext", () => ({
  useSidebar: () => ({
    collapsed: false,
    toggleCollapsed: () => {},
    mobileOpen: false,
    setMobileOpen,
  }),
}));

import { MobileNav } from "./MobileNav";
import { MOBILE_PRIMARY_NAV, NAV_ITEMS } from "@/lib/navigation";

afterEach(() => {
  cleanup();
  currentPath = "/";
  setMobileOpen.mockClear();
});

describe("MobileNav — Sprint 036", () => {
  it("shows at most five targets so each one stays thumb-sized at 360px", () => {
    render(<MobileNav />);

    const nav = screen.getByRole("navigation", { name: "Primary" });
    const targets = nav.querySelectorAll("a, button");
    expect(targets.length).toBeLessThanOrEqual(5);
    expect(MOBILE_PRIMARY_NAV.length).toBe(4);
  });

  it("carries the highest-frequency destinations and a way to the rest", () => {
    render(<MobileNav />);

    for (const item of MOBILE_PRIMARY_NAV) {
      expect(screen.getByRole("link", { name: item.label })).toBeInTheDocument();
    }
    expect(screen.getByLabelText("More navigation")).toBeInTheDocument();
    // Everything not in the bottom bar is still reachable — through the
    // drawer, which "More" opens.
    expect(NAV_ITEMS.length).toBeGreaterThan(MOBILE_PRIMARY_NAV.length);
  });

  it("announces the current page rather than only colouring it", () => {
    currentPath = "/quotes";
    render(<MobileNav />);

    const quotes = screen.getByRole("link", { name: "Quotes" });
    expect(quotes).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current"
    );
  });

  it("does not treat every route as the dashboard", () => {
    currentPath = "/customers";
    render(<MobileNav />);

    // "/" would prefix-match every path — the dashboard has to be an
    // exact match or it is permanently highlighted.
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current"
    );
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("is hidden from tablet up, where the rail replaces it", () => {
    render(<MobileNav />);
    expect(screen.getByRole("navigation", { name: "Primary" }).className).toContain(
      "md:hidden"
    );
  });
});
