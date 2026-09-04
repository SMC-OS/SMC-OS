"use client";

import { createContext, useContext, useEffect, useState } from "react";

import {
  LEGACY_THEME_KEY,
  THEME_KEY,
  readMigratedValue,
  writeValue,
} from "@/lib/storage-keys";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

// Sprint 034 (Phase 2) — renamed with the platform, read through the
// migration helper so an existing user's chosen theme survives the deploy.
const STORAGE_KEY = THEME_KEY;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);

  // Read the persisted/system preference once, client-side only.
  // The inline script in layout.tsx already set the class on <html> before
  // paint, so this just syncs React state to match — no flash of the wrong
  // theme.
  useEffect(() => {
    // One-time sync from browser-only APIs (localStorage/matchMedia aren't
    // available during SSR). The inline script in layout.tsx already set the
    // class on <html> before paint, so this just syncs React state to match.
    const stored = readMigratedValue(STORAGE_KEY, LEGACY_THEME_KEY) as Theme | null;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setThemeState(stored ?? (prefersDark ? "dark" : "light"));
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    document.documentElement.classList.toggle("dark", theme === "dark");
    writeValue(STORAGE_KEY, theme);
  }, [theme, mounted]);

  const setTheme = (next: Theme) => setThemeState(next);
  const toggleTheme = () =>
    setThemeState((prev) => (prev === "dark" ? "light" : "dark"));

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
