/**
 * Sprint 036 (Workstream B/M) — the reported phone bug: the theme control
 * appeared to sit inside the global search field.
 *
 * The cause was flex sizing, not z-index or positioning (see Topbar's own
 * docstring), so this file locks in the structural facts that make the
 * overflow impossible rather than asserting on computed pixels, which
 * jsdom does not lay out.
 *
 * The regression this guards: if someone reintroduces `w-full max-w-xs`
 * on the search control, or drops `flex-1 min-w-0` from the group that
 * holds it, or removes the phone-only icon variant, the left group's
 * intrinsic width can once again exceed the space left by the right-hand
 * cluster and the controls overlap at 360-412px.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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

let currentTheme = "light";
const toggleTheme = vi.fn();
vi.mock("@/components/theme/ThemeProvider", () => ({
  useTheme: () => ({ theme: currentTheme, toggleTheme }),
}));

vi.mock("@/components/shell/NotificationsPanel", () => ({
  NotificationsPanel: () => <button type="button">Notifications</button>,
}));
vi.mock("@/components/shell/UserProfileMenu", () => ({
  UserProfileMenu: () => <button type="button">Profile</button>,
}));
vi.mock("@/components/shell/CommandPalette", () => ({
  CommandPalette: () => null,
}));

import { Topbar } from "./Topbar";

afterEach(() => {
  cleanup();
  currentTheme = "light";
});

describe("Topbar — theme/search overlap regression (Sprint 036)", () => {
  it("gives the search control room to shrink instead of forcing a fixed width", () => {
    const { container } = render(<Topbar />);

    const group = container.querySelector("header > div");
    expect(group).not.toBeNull();
    // Without both of these the group asks for its content width and
    // pushes into the right-hand cluster.
    expect(group!.className).toContain("flex-1");
    expect(group!.className).toContain("min-w-0");

    const wideSearch = screen.getByText("Search pages and actions…").closest("button");
    expect(wideSearch).not.toBeNull();
    expect(wideSearch!.className).toContain("min-w-0");
    // The exact class that caused the bug.
    expect(wideSearch!.className).not.toContain("w-full");
    expect(wideSearch!.className).not.toContain("max-w-xs");
  });

  it("offers search as an icon on phones and a labelled field from sm up", () => {
    render(<Topbar />);

    // Both exist in the DOM; the breakpoint classes decide which is
    // visible. Asserting on the pair is what proves the phone layout is
    // a deliberate variant rather than a squeezed field.
    const iconSearch = screen.getByLabelText("Search pages and actions");
    expect(iconSearch.className).toContain("sm:hidden");

    const wideSearch = screen.getByText("Search pages and actions…").closest("button");
    expect(wideSearch!.className).toContain("hidden");
    expect(wideSearch!.className).toContain("sm:flex");
  });

  it("keeps the right-hand controls from being compressed", () => {
    const { container } = render(<Topbar />);

    const controls = container.querySelectorAll("header > div")[1];
    expect(controls.className).toContain("shrink-0");
  });

  it("labels the theme control with what it will do, not what it is", () => {
    render(<Topbar />);
    expect(screen.getByLabelText("Switch to dark mode")).toBeInTheDocument();

    cleanup();
    currentTheme = "dark";
    render(<Topbar />);
    expect(screen.getByLabelText("Switch to light mode")).toBeInTheDocument();
  });

  it("gives every top bar control a 40px touch target", () => {
    render(<Topbar />);

    for (const label of [
      "Open menu",
      "Search pages and actions",
      "Switch to dark mode",
    ]) {
      // 40px (h-10 w-10) is the minimum this design uses for a
      // tap target; below that a thumb misses it on a phone.
      expect(screen.getByLabelText(label).className).toContain("h-10");
      expect(screen.getByLabelText(label).className).toContain("w-10");
    }
  });
});
