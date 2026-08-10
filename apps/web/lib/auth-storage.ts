/**
 * Plain (non-React) localStorage wrapper for the JWT issued by
 * POST /api/v1/auth/login. Kept outside React so lib/api.ts can read the
 * token directly, without a component-tree dependency on a context.
 *
 * Sprint 004 — see components/auth/AuthProvider.tsx for the React-facing
 * layer built on top of this.
 */

const STORAGE_KEY = "simo-os-token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(STORAGE_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(STORAGE_KEY);
}
