"use client";

import { useState } from "react";

import { CommandPalette } from "@/components/shell/CommandPalette";
import { NotificationsPanel } from "@/components/shell/NotificationsPanel";
import { UserProfileMenu } from "@/components/shell/UserProfileMenu";
import { useTheme } from "@/components/theme/ThemeProvider";
import { MenuIcon, MoonIcon, SearchIcon, SunIcon } from "@/components/ui/icons";

import { useSidebar } from "./SidebarContext";

/**
 * Sprint 036 (Workstream B/M) — this component carried the reported bug
 * where the theme control appeared to sit inside the global search field
 * on a phone.
 *
 * Root cause (found by reading the layout, not by nudging pixels): the
 * header is `flex justify-between`; the left group had `min-w-0` but the
 * search button inside it was `w-full max-w-xs` while the group itself
 * had neither `flex-1` nor a min-width of its own. At 360–412px the left
 * group's intrinsic width (36px menu + gap + up to 320px of search)
 * exceeded the space left by the right-hand `shrink-0` control cluster,
 * so the search field overflowed underneath the theme and notification
 * buttons. It was a flex-sizing bug, not a z-index or positioning one.
 *
 * The fix, and why each part of it is load-bearing:
 *   - the left group is `flex-1 min-w-0`, so it takes the space that is
 *     actually left over rather than asking for a fixed 320px;
 *   - the search control is `min-w-0`, so it is allowed to shrink below
 *     its content width instead of forcing the group wider;
 *   - below `sm` the search collapses to a single icon button, because
 *     there genuinely is not room for a labelled field, a menu button and
 *     three controls at 360px — and a cramped field is worse than a clear
 *     icon;
 *   - the right cluster keeps `shrink-0` so its touch targets never
 *     compress.
 */
export function Topbar() {
  const { setMobileOpen } = useSidebar();
  const { theme, toggleTheme } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header className="flex h-16 shrink-0 items-center gap-2 border-b border-border bg-surface px-3 sm:gap-3 sm:px-4 lg:px-6">
      <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface-hover hover:text-foreground md:hidden"
          aria-label="Open menu"
        >
          <MenuIcon className="h-[18px] w-[18px]" />
        </button>

        {/* Phone: an icon. There is no room for a labelled field here. */}
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface-hover hover:text-foreground sm:hidden"
          aria-label="Search pages and actions"
        >
          <SearchIcon className="h-[18px] w-[18px]" />
        </button>

        {/* Tablet and up: the full field. */}
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="hidden h-10 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3 text-sm text-muted transition-colors hover:border-border-strong sm:flex sm:max-w-sm lg:max-w-md"
        >
          <SearchIcon className="h-4 w-4 shrink-0" />
          <span className="truncate">Search pages and actions…</span>
          <kbd className="ml-auto hidden shrink-0 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] lg:block">
            &#8984;K
          </kbd>
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-0.5 sm:gap-1.5">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted hover:bg-surface-hover hover:text-foreground"
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? (
            <SunIcon className="h-[18px] w-[18px]" />
          ) : (
            <MoonIcon className="h-[18px] w-[18px]" />
          )}
        </button>

        <NotificationsPanel />

        <div className="mx-1 hidden h-6 w-px bg-border sm:block" />

        <UserProfileMenu />
      </div>

      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </header>
  );
}
