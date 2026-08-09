"use client";

import { useState } from "react";

import { CommandPalette } from "@/components/shell/CommandPalette";
import { NotificationsPanel } from "@/components/shell/NotificationsPanel";
import { UserProfileMenu } from "@/components/shell/UserProfileMenu";
import { useTheme } from "@/components/theme/ThemeProvider";
import { MenuIcon, MoonIcon, SearchIcon, SunIcon } from "@/components/ui/icons";

import { useSidebar } from "./SidebarContext";

export function Topbar() {
  const { setMobileOpen } = useSidebar();
  const { theme, toggleTheme } = useTheme();
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 lg:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-surface-hover lg:hidden"
          aria-label="Open menu"
        >
          <MenuIcon className="h-[18px] w-[18px]" />
        </button>

        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="flex w-full max-w-xs items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm text-muted hover:border-accent/50 sm:max-w-sm"
        >
          <SearchIcon className="h-4 w-4 shrink-0" />
          <span className="truncate">Search pages and actions…</span>
          <kbd className="ml-auto hidden shrink-0 rounded border border-border bg-surface px-1.5 py-0.5 text-[10px] sm:block">
            &#8984;K
          </kbd>
        </button>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-surface-hover hover:text-foreground"
          aria-label="Toggle dark mode"
        >
          {theme === "dark" ? (
            <SunIcon className="h-[18px] w-[18px]" />
          ) : (
            <MoonIcon className="h-[18px] w-[18px]" />
          )}
        </button>

        <NotificationsPanel />

        <div className="mx-1 h-6 w-px bg-border" />

        <UserProfileMenu />
      </div>

      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </header>
  );
}
