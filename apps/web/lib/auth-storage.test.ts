/**
 * Production incident (post-v1.0.1): the dashboard kept presenting a
 * signed-in user after their token expired mid-session — a stale/expired
 * JWT gets a 401 from the API, lib/api.ts's request() correctly clears the
 * stored token, but nothing tells AuthProvider's React state that this
 * happened. clearToken() needs to announce itself so AuthProvider (and any
 * other subscriber) can react to a session becoming invalid at any time,
 * not just on initial mount.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken, getToken, clearLegacyTokens, TOKEN_CLEARED_EVENT } from "@/lib/auth-storage";

afterEach(() => {
  clearToken();
  window.localStorage.clear();
});

describe("auth-storage — token-cleared notification", () => {
  it("dispatches TOKEN_CLEARED_EVENT on window when clearToken runs", () => {
    setToken("a-token");
    const listener = vi.fn();
    window.addEventListener(TOKEN_CLEARED_EVENT, listener);

    clearToken();

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(TOKEN_CLEARED_EVENT, listener);
  });

  it("still removes the token from localStorage as before", () => {
    setToken("a-token");

    clearToken();

    expect(window.localStorage.getItem("geocore-token")).toBeNull();
  });
});

it("never persists the explicit in-memory bearer seam in browser storage", () => {
  setToken("synthetic-private-token");
  expect(getToken()).toBe("synthetic-private-token");
  expect(localStorage.getItem("geocore-token")).toBeNull();
  expect(sessionStorage.getItem("geocore-token")).toBeNull();
});
it("discards old bearer storage without authenticating from it", () => {
  localStorage.setItem("geocore-token", "retired-token");
  localStorage.setItem("simo-os-token", "retired-legacy-token");
  expect(getToken()).toBeNull();
  clearLegacyTokens();
  expect(localStorage.getItem("geocore-token")).toBeNull();
});
