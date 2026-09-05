"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { MenuIcon } from "@/components/ui/icons";
import { MOBILE_PRIMARY_NAV } from "@/lib/navigation";
import { cn } from "@/lib/utils";

import { useSidebar } from "./SidebarContext";

/**
 * The phone bottom bar (Sprint 036, Workstream A/M).
 *
 * Four destinations plus "More". Five slots is the practical limit at
 * 360px: below that each target falls under the ~44px that a thumb can
 * reliably hit, and a navigation control you have to aim at is worse than
 * one extra tap through the drawer.
 *
 * It sits above the iOS home indicator via env(safe-area-inset-bottom),
 * and AppShell reserves matching padding at the bottom of the scroll area
 * so this bar never covers the last row of a list or the submit button of
 * a form.
 */
export function MobileNav() {
  const pathname = usePathname();
  const { setMobileOpen } = useSidebar();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="flex items-stretch">
        {MOBILE_PRIMARY_NAV.map((item) => {
          const active = isActive(item.href);
          const ItemIcon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-w-0 flex-1 flex-col items-center justify-center gap-1 py-2.5 text-[11px] font-medium transition-colors",
                active ? "text-accent" : "text-muted"
              )}
            >
              <ItemIcon className="h-5 w-5 shrink-0" />
              <span className="w-full truncate px-1 text-center">{item.label}</span>
            </Link>
          );
        })}

        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="flex min-w-0 flex-1 flex-col items-center justify-center gap-1 py-2.5 text-[11px] font-medium text-muted"
          aria-label="More navigation"
        >
          <MenuIcon className="h-5 w-5 shrink-0" />
          <span>More</span>
        </button>
      </div>
    </nav>
  );
}
