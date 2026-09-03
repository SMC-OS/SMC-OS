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

import { clearToken, setToken, TOKEN_CLEARED_EVENT } from "@/lib/auth-storage";

afterEach(() => {
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

    expect(window.localStorage.getItem("simo-os-token")).toBeNull();
  });
});
