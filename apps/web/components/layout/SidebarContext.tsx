"use client";

import { createContext, useContext, useEffect, useState } from "react";

import {
  LEGACY_SIDEBAR_COLLAPSED_KEY,
  SIDEBAR_COLLAPSED_KEY,
  readMigratedValue,
  writeValue,
} from "@/lib/storage-keys";

interface SidebarContextValue {
  collapsed: boolean;
  toggleCollapsed: () => void;
  mobileOpen: boolean;
  setMobileOpen: (open: boolean) => void;
}

const SidebarContext = createContext<SidebarContextValue | undefined>(undefined);

// Sprint 034 (Phase 2) — renamed with the platform; see lib/storage-keys.ts.
const STORAGE_KEY = SIDEBAR_COLLAPSED_KEY;

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    // One-time sync from a browser-only API (localStorage isn't available
    // during SSR, so this can't be a lazy useState initializer).
    const stored = readMigratedValue(STORAGE_KEY, LEGACY_SIDEBAR_COLLAPSED_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setCollapsed(stored === "true");
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      writeValue(STORAGE_KEY, String(next));
      return next;
    });
  };

  return (
    <SidebarContext.Provider
      value={{ collapsed, toggleCollapsed, mobileOpen, setMobileOpen }}
    >
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error("useSidebar must be used within a SidebarProvider");
  return ctx;
}
