/** Theme rebrand migration stays compatible. SEC001 deliberately retires
 * both historical bearer stores: browser authentication is now HttpOnly. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, clearLegacyTokens, getToken, setToken } from "@/lib/auth-storage";
import {
  LEGACY_THEME_KEY,
  LEGACY_TOKEN_KEY,
  THEME_KEY,
  TOKEN_KEY,
  readMigratedValue,
} from "@/lib/storage-keys";

beforeEach(() => {
  clearToken();
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("readMigratedValue", () => {
  it("prefers_the_current_key_when_both_exist", () => {
    window.localStorage.setItem(THEME_KEY, "dark");
    window.localStorage.setItem(LEGACY_THEME_KEY, "light");

    expect(readMigratedValue(THEME_KEY, LEGACY_THEME_KEY)).toBe("dark");
    // The stale legacy value is left alone rather than overwriting the
    // newer one — this path is not a migration, it is a normal read.
    expect(window.localStorage.getItem(LEGACY_THEME_KEY)).toBe("light");
  });

  it("falls_back_to_the_legacy_key_and_carries_the_value_forward", () => {
    window.localStorage.setItem(LEGACY_THEME_KEY, "dark");

    expect(readMigratedValue(THEME_KEY, LEGACY_THEME_KEY)).toBe("dark");
    expect(window.localStorage.getItem(THEME_KEY)).toBe("dark");
    // Migrated exactly once — the legacy key is gone afterwards.
    expect(window.localStorage.getItem(LEGACY_THEME_KEY)).toBeNull();
  });

  it("returns_null_when_neither_key_exists", () => {
    expect(readMigratedValue(THEME_KEY, LEGACY_THEME_KEY)).toBeNull();
  });

  it("still_returns_the_value_when_the_migrating_write_fails", () => {
    // Safari private mode and "block all cookies" make setItem throw. A
    // failed migration must not cost the caller a valid value.
    window.localStorage.setItem(LEGACY_TOKEN_KEY, "jwt-abc");
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });

    expect(readMigratedValue(TOKEN_KEY, LEGACY_TOKEN_KEY)).toBe("jwt-abc");
  });

  it("returns_null_rather_than_throwing_when_storage_is_unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });

    expect(() => readMigratedValue(TOKEN_KEY, LEGACY_TOKEN_KEY)).not.toThrow();
    expect(readMigratedValue(TOKEN_KEY, LEGACY_TOKEN_KEY)).toBeNull();
  });
});

describe("retired browser bearer stores", () => {
  it("legacy_browser_bearers_are_discarded_and_never_restored", () => {
    // Exactly the state a real browser is in at deploy time.
    window.localStorage.setItem(LEGACY_TOKEN_KEY, "pre-rebrand-jwt");

    clearLegacyTokens();
    expect(getToken()).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(LEGACY_TOKEN_KEY)).toBeNull();
  });

  it("sign_out_clears_the_legacy_key_too", () => {
    // Otherwise clearToken() would leave a valid JWT under the old name for
    // the very next getToken() to migrate back in — a sign-out that doesn't.
    window.localStorage.setItem(LEGACY_TOKEN_KEY, "pre-rebrand-jwt");
    setToken("current-jwt");

    clearToken();

    expect(getToken()).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(LEGACY_TOKEN_KEY)).toBeNull();
  });

  it("explicit_memory_bearers_never_write_browser_storage", () => {
    setToken("fresh-jwt");

    expect(getToken()).toBe("fresh-jwt");
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(LEGACY_TOKEN_KEY)).toBeNull();
  });
});
