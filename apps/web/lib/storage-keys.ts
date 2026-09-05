/**
 * Sprint 034 (Phase 2) — localStorage keys, and the one-time migration
 * from their pre-rebrand `simo-os-*` names.
 *
 * Renaming a persisted key is not a cosmetic change: every one of these
 * already exists in a real browser right now. A naive rename would silently
 * reset every user's theme and sidebar preference and — far worse — log
 * every signed-in user out, because `getToken()` would stop finding the JWT
 * that is sitting in the old key.
 *
 * So each key is read through `readMigratedValue()`, which prefers the new
 * key, falls back to the legacy one exactly once, and carries the value
 * forward. After a user's first page load post-deploy the legacy key is
 * gone and the fallback never fires again.
 *
 * Every accessor is wrapped in try/catch: Safari private mode and
 * "block all cookies" settings make `localStorage` itself throw on access,
 * and a thrown storage read during module init would take the whole app
 * down rather than degrade to a signed-out state.
 */

export const TOKEN_KEY = "geocore-token";
export const THEME_KEY = "geocore-theme";
export const SIDEBAR_COLLAPSED_KEY = "geocore-sidebar-collapsed";
// Sprint 036 — in-app notification preferences. New in this release, so
// it has no legacy counterpart to migrate from.
export const NOTIFICATION_PREFERENCE_KEY = "geocore-notification-preferences";

export const LEGACY_TOKEN_KEY = "simo-os-token";
export const LEGACY_THEME_KEY = "simo-os-theme";
export const LEGACY_SIDEBAR_COLLAPSED_KEY = "simo-os-sidebar-collapsed";

/**
 * Read `key`, falling back to `legacyKey` and migrating the value forward.
 *
 * Returns null when neither exists, or when storage is unavailable.
 */
export function readMigratedValue(key: string, legacyKey: string): string | null {
  if (typeof window === "undefined") return null;

  try {
    const current = window.localStorage.getItem(key);
    if (current !== null) return current;

    const legacy = window.localStorage.getItem(legacyKey);
    if (legacy === null) return null;

    // Carry it forward, then drop the old key. Wrapped separately so a
    // write failure (quota, private mode) still returns the value the
    // caller asked for rather than throwing away a valid session.
    try {
      window.localStorage.setItem(key, legacy);
      window.localStorage.removeItem(legacyKey);
    } catch {
      // Migration is best-effort; the value below is still correct.
    }

    return legacy;
  } catch {
    return null;
  }
}

/**
 * Read a key that has no legacy counterpart (Sprint 036). Same
 * storage-may-throw handling as readMigratedValue, without the migration.
 */
export function readValue(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeValue(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable — the app stays functional for this session.
  }
}

/** Removes both the current and legacy key, so a sign-out is complete. */
export function removeValue(key: string, legacyKey: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
    window.localStorage.removeItem(legacyKey);
  } catch {
    // Nothing to do — see the note above.
  }
}
