"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/auth/AuthProvider";

import { MobileNav } from "./MobileNav";
import { SidebarProvider } from "./SidebarContext";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/**
 * The shell every page in the app renders inside of (wired in
 * app/layout.tsx). A new module only needs a route under app/; it does
 * not need to touch this file to get navigation, search, notifications,
 * theming or the responsive treatment.
 *
 * Sprint 036 (Workstream A/M):
 *   - `min-w-0` on the content column is what actually stops a wide table
 *     or a long unbroken string from pushing the whole page sideways: a
 *     flex child's default min-width is `auto`, i.e. its content, so
 *     without this the shell grows and the body scrolls horizontally.
 *   - the scroll area reserves bottom padding on phones for the fixed
 *     bottom navigation, so the last row of a list and the submit button
 *     of a form are never sitting underneath it.
 *   - `pb-[env(safe-area-inset-bottom)]` handles the iOS home indicator
 *     on top of that.
 *
 * Sprint 039 V1 — the Demo Workspace is reached from marketing and the
 * login page with "no account needed". The real Sidebar/Topbar link to
 * authenticated routes (Dashboard, Customers, an actual "Account" menu)
 * that a demo visitor has no session for — clicking any of them silently
 * bounces to /login, which is a dead end for exactly the audience this
 * entry point targets. It renders standalone instead, with no chrome
 * pointing anywhere but itself.
 */
const STANDALONE_ROUTES = ["/demo"];

// Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — routes an
// unverified-but-authenticated user must still be able to reach: signing in
// or out, the public auth-lifecycle pages, and the verification screen
// itself (redirecting away from /verify-email TO /verify-email would loop).
// Deliberately the same allowlist app/auth/router.py enforces server-side
// (plus /pricing and /portal, which need no verification at all — /pricing
// is publicly browsable and /portal is customer-facing, not this tenant's
// own session). This is UX routing only; the backend is the real boundary
// (see app/auth/dependencies.py's require_verified_email) — a user who
// bypasses this redirect still gets a 403 from every protected route.
const VERIFICATION_EXEMPT_ROUTES = [
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/invite",
  "/portal",
  "/pricing",
  "/demo",
];

function matchesRoute(pathname: string | null, routes: string[]): boolean {
  if (!pathname) return false;
  return routes.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

function isStandaloneRoute(pathname: string | null): boolean {
  return matchesRoute(pathname, STANDALONE_ROUTES);
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isReady, isAuthenticated, verificationRequired } = useAuth();

  useEffect(() => {
    if (!isReady || !isAuthenticated || !verificationRequired) return;
    if (matchesRoute(pathname, VERIFICATION_EXEMPT_ROUTES)) return;
    router.replace("/verify-email");
  }, [isReady, isAuthenticated, verificationRequired, pathname, router]);

  if (isStandaloneRoute(pathname)) {
    return <div className="min-h-screen overflow-y-auto bg-background">{children}</div>;
  }

  return (
    <SidebarProvider>
      <div className="flex h-screen overflow-hidden bg-background">
        <Sidebar />

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />

          <main
            className="min-w-0 flex-1 overflow-y-auto p-4 pb-24 md:pb-8 lg:p-8"
            style={{ scrollPaddingBottom: "6rem" }}
          >
            {children}
          </main>
        </div>

        <MobileNav />
      </div>
    </SidebarProvider>
  );
}
