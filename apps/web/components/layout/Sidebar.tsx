"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  SettingsIcon,
} from "@/components/ui/icons";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { useSidebar } from "./SidebarContext";

/**
 * Sprint 036 (Workstream A/M) — three genuinely different navigation
 * treatments, not one treatment with a media query bolted on:
 *
 *   phone   (<768px)  a drawer, opened from the top bar, plus a bottom bar
 *                     of the four highest-frequency destinations
 *                     (components/layout/MobileNav.tsx).
 *   tablet  (768–1023) an always-visible icon rail. A tablet has room for
 *                     persistent navigation but not for a 256px sidebar
 *                     next to a form — the previous build gave this range
 *                     the phone drawer, which wasted the space entirely.
 *   desktop (≥1024)   the full sidebar, collapsible to a rail.
 *
 * The logo artwork is unchanged — Sprint 035's official brand assets are
 * rendered as-is, never recoloured or redrawn.
 */

function useIsActive() {
  const pathname = usePathname();
  return (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function BrandMark({ showWordmark }: { showWordmark: boolean }) {
  return (
    <>
      <Image
        src="/brand/monogram.png"
        alt="GeoCore"
        width={32}
        height={32}
        className="h-8 w-8 shrink-0 object-contain"
        priority
      />
      {showWordmark && (
        <div className="min-w-0 overflow-hidden">
          <p className="truncate text-sm font-semibold text-foreground">GeoCore</p>
          <p className="truncate text-xs text-muted">Build smarter together</p>
        </div>
      )}
    </>
  );
}

function NavLinks({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const isActive = useIsActive();

  return (
    <nav
      aria-label="Main"
      className="flex-1 space-y-1 overflow-y-auto p-3"
    >
      {NAV_ITEMS.map((item) => {
        const active = isActive(item.href);
        const ItemIcon = item.icon;

        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            // aria-current is what tells a screen reader which page it is
            // on. The colour change alone says nothing.
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              collapsed && "justify-center px-0",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted hover:bg-surface-hover hover:text-foreground"
            )}
            title={collapsed ? item.label : undefined}
          >
            <ItemIcon className="h-[18px] w-[18px] shrink-0" />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

function SettingsLink({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const isActive = useIsActive();
  const active = isActive("/settings");

  return (
    <div className="border-t border-border p-3">
      <Link
        href="/settings"
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
          collapsed && "justify-center px-0",
          active
            ? "bg-accent text-accent-foreground"
            : "text-muted hover:bg-surface-hover hover:text-foreground"
        )}
        title={collapsed ? "Settings" : undefined}
      >
        <SettingsIcon className="h-[18px] w-[18px] shrink-0" />
        {!collapsed && <span className="truncate">Settings</span>}
      </Link>
    </div>
  );
}

function SidebarContents({
  collapsed,
  onNavigate,
  showCollapseToggle,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  showCollapseToggle?: boolean;
}) {
  const { toggleCollapsed } = useSidebar();

  return (
    <>
      <div
        className={cn(
          "flex items-center gap-2 border-b border-border p-4",
          collapsed ? "justify-center" : "justify-between"
        )}
      >
        <Link
          href="/"
          className="flex min-w-0 items-center gap-2.5 overflow-hidden"
          onClick={onNavigate}
        >
          <BrandMark showWordmark={!collapsed} />
        </Link>

        {showCollapseToggle && !collapsed && (
          <button
            type="button"
            onClick={toggleCollapsed}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-foreground"
            aria-label="Collapse sidebar"
          >
            <ChevronLeftIcon className="h-4 w-4" />
          </button>
        )}
      </div>

      {showCollapseToggle && collapsed && (
        <button
          type="button"
          onClick={toggleCollapsed}
          className="mx-auto mt-2 flex h-7 w-7 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-foreground"
          aria-label="Expand sidebar"
        >
          <ChevronRightIcon className="h-4 w-4" />
        </button>
      )}

      <NavLinks collapsed={collapsed} onNavigate={onNavigate} />
      <SettingsLink collapsed={collapsed} onNavigate={onNavigate} />
    </>
  );
}

export function Sidebar() {
  const { collapsed, mobileOpen, setMobileOpen } = useSidebar();

  return (
    <>
      {/* Tablet: a permanent icon rail. Deliberately not collapsible —
          at this width there is no second state worth offering, and a
          rail that can become a sidebar would leave a form 200px wide. */}
      <aside className="hidden w-[68px] shrink-0 flex-col border-r border-border bg-surface md:flex lg:hidden">
        <SidebarContents collapsed />
      </aside>

      {/* Desktop: the full sidebar. */}
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 lg:flex",
          collapsed ? "w-[76px]" : "w-64"
        )}
      >
        <SidebarContents collapsed={collapsed} showCollapseToggle />
      </aside>

      {/* Phone: an overlay drawer. */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            // max-w-[85vw] so the drawer never covers the whole screen on
            // a 320px device — there is always visible page behind it to
            // tap back to.
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-xl"
          >
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="flex h-10 w-10 items-center justify-center rounded-md text-muted hover:bg-surface-hover"
                aria-label="Close menu"
              >
                <CloseIcon className="h-4 w-4" />
              </button>
            </div>
            <SidebarContents collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
