"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { ChevronDownIcon, LogOutIcon, SettingsIcon, UserIcon } from "@/components/ui/icons";
import { useClickOutside } from "@/hooks/useClickOutside";

export function UserProfileMenu() {
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false));
  const router = useRouter();
  const { logout, name, role, tenantName } = useAuth();
  // Sprint 028 (UAT-001) — real values once resolved; a neutral fallback
  // only for the brief window before AuthProvider's own mount effect
  // resolves them (never a fabricated identity).
  const displayName = name ?? "Account";
  const displayRole = role ?? "";
  const displayTenant = tenantName ?? "";

  async function handleSignOut() {
    setSigningOut(true);
    setLogoutError(null);
    try {
      await logout();
      setOpen(false);
      router.push("/login");
    } catch {
      setLogoutError("Could not sign out. Check your connection and try again.");
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 hover:bg-surface-hover"
      >
        <Avatar name={displayName} />
        <span className="hidden text-left sm:block">
          <span className="block text-sm font-medium leading-tight text-foreground">
            {displayName}
          </span>
          <span className="block text-xs leading-tight text-muted">{displayRole}</span>
        </span>
        <ChevronDownIcon className="hidden h-4 w-4 text-muted sm:block" />
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-56 rounded-xl border border-border bg-surface p-1.5 shadow-lg">
          <div className="border-b border-border px-2.5 py-2">
            <p className="text-sm font-medium text-foreground">{displayName}</p>
            <p className="text-xs text-muted">{displayTenant}</p>
          </div>

          <button
            type="button"
            disabled
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-muted opacity-60"
            title="Profile management isn't built yet"
          >
            <UserIcon className="h-4 w-4" />
            Profile
          </button>

          <button
            type="button"
            disabled
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-muted opacity-60"
            title="No account settings to configure yet"
          >
            <SettingsIcon className="h-4 w-4" />
            Settings
          </button>

          <button
            type="button"
            onClick={handleSignOut}
            disabled={signingOut}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-foreground hover:bg-surface-hover"
          >
            <LogOutIcon className="h-4 w-4" />
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
          {logoutError && <p role="alert" className="px-2.5 py-2 text-xs text-danger">{logoutError}</p>}
        </div>
      )}
    </div>
  );
}
