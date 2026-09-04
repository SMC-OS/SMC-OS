"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { ChevronLeftIcon, ChevronRightIcon, CloseIcon } from "@/components/ui/icons";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { useSidebar } from "./SidebarContext";

function SidebarContents({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { collapsed, toggleCollapsed } = useSidebar();

  return (
    <>
      <div className="flex items-center justify-between border-b border-border p-4">
        <Link href="/" className="flex items-center gap-2 overflow-hidden" onClick={onNavigate}>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-foreground">
            S
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <p className="truncate text-sm font-semibold text-foreground">
                GeoCore
              </p>
              <p className="truncate text-xs text-muted">AI Operating System</p>
            </div>
          )}
        </Link>

        <button
          type="button"
          onClick={toggleCollapsed}
          className="hidden h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-hover hover:text-foreground lg:flex"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <ChevronRightIcon className="h-4 w-4" />
          ) : (
            <ChevronLeftIcon className="h-4 w-4" />
          )}
        </button>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const ItemIcon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
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
    </>
  );
}

export function Sidebar() {
  const { collapsed, mobileOpen, setMobileOpen } = useSidebar();

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 lg:flex",
          collapsed ? "w-[76px]" : "w-64"
        )}
      >
        <SidebarContents />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-72 flex-col bg-surface shadow-xl">
            <div className="flex justify-end p-2">
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-hover"
                aria-label="Close menu"
              >
                <CloseIcon className="h-4 w-4" />
              </button>
            </div>
            <SidebarContents onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
