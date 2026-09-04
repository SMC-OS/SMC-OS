/**
 * Plain (non-React) localStorage wrapper for the JWT issued by
 * POST /api/v1/auth/login. Kept outside React so lib/api.ts can read the
 * token directly, without a component-tree dependency on a context.
 *
 * Sprint 004 — see components/auth/AuthProvider.tsx for the React-facing
 * layer built on top of this.
 */

import {
  LEGACY_TOKEN_KEY,
  TOKEN_KEY,
  readMigratedValue,
  removeValue,
  writeValue,
} from "@/lib/storage-keys";

// Sprint 034 (Phase 2) — the key was renamed with the platform. It is read
// through readMigratedValue() so an already-signed-in user keeps their
// session across the rebrand deploy instead of being logged out.
const STORAGE_KEY = TOKEN_KEY;

// Production incident (post-v1.0.1): clearToken() used to only touch
// localStorage, so AuthProvider — which only checks the token once, on
// mount — never learned that a session had gone invalid (e.g. a 401 from
// an expired JWT during lib/api.ts's request()). Dispatching this event
// lets AuthProvider (or anything else) react the moment a token is
// cleared, not just at page load.
export const TOKEN_CLEARED_EVENT = "geocore:token-cleared";

export function getToken(): string | null {
  return readMigratedValue(STORAGE_KEY, LEGACY_TOKEN_KEY);
}

export function setToken(token: string): void {
  writeValue(STORAGE_KEY, token);
}

export function clearToken(): void {
  // Clears the legacy key too — otherwise a sign-out would leave a valid
  // JWT behind under the old name for readMigratedValue() to find again.
  removeValue(STORAGE_KEY, LEGACY_TOKEN_KEY);
  window.dispatchEvent(new Event(TOKEN_CLEARED_EVENT));
}
