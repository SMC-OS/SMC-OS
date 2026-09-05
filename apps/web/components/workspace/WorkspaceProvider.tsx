"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { api } from "@/lib/api";
import type { TenantProfile } from "@/types/tenant";

interface WorkspaceContextValue {
  profile: TenantProfile | null;
  /** The workspace's currency, defaulted to GBP until the profile loads.
   * Every money format in the app reads this rather than hardcoding a
   * currency at the call site. */
  currency: string;
  loading: boolean;
  refresh: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

/**
 * Sprint 036 — one fetch of the workspace profile, shared by everything
 * that needs to know how this business is configured.
 *
 * Why a provider rather than a hook each page calls: currency appears on
 * the dashboard, every quote, every project and the customer page, and
 * fetching it per component would issue the same request five times on a
 * single page load. This fetches once per session and re-fetches only
 * when something changes it (settings, onboarding).
 *
 * GBP is the fallback while loading and if the request fails. That is the
 * honest default — every workspace on GeoCore today is a UK business —
 * and it means a transient network failure renders slightly-wrong symbols
 * rather than an error page over the whole application.
 */
export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isReady } = useAuth();
  const [profile, setProfile] = useState<TenantProfile | null>(null);
  const [settled, setSettled] = useState(false);
  // Bumped by refresh() to re-run the fetch effect. A counter rather than
  // calling a loader function directly: every state write then happens in
  // a promise callback or an event handler, never synchronously inside an
  // effect body, which is what the repo's react-hooks/set-state-in-effect
  // rule requires (a sync setState in an effect causes a cascading
  // render).
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!isReady || !isAuthenticated) return;

    // Guarded so a response arriving after sign-out — or after a second
    // refresh overtook this one — cannot write stale data into state.
    let cancelled = false;
    api
      .getCompanyProfile()
      .then((next) => {
        if (cancelled) return;
        setProfile(next);
        setSettled(true);
      })
      .catch(() => {
        if (cancelled) return;
        setProfile(null);
        setSettled(true);
      });

    return () => {
      cancelled = true;
    };
  }, [isReady, isAuthenticated, reloadToken]);

  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  // Derived rather than stored: a signed-out viewer must never see the
  // previous session's workspace, and deriving it makes that true by
  // construction instead of depending on a cleanup effect running.
  const visibleProfile = isAuthenticated ? profile : null;

  return (
    <WorkspaceContext.Provider
      value={{
        profile: visibleProfile,
        currency: visibleProfile?.currency ?? "GBP",
        loading: isAuthenticated && !settled,
        refresh,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    // Deliberately not throwing: a component rendered outside the
    // provider (a test harness, a public page like /invite or /portal)
    // should still render with sensible defaults rather than crash.
    return { profile: null, currency: "GBP", loading: false, refresh: () => {} };
  }
  return ctx;
}
