/**
 * Production incident (post-v1.0.1): the dashboard reported an expired
 * session ("Request to /dashboard failed with 401") as "Couldn't reach the
 * SIMO OS API" — the same generic message used for a real network/API
 * outage. A 401/403 is an auth problem, not an availability problem, and
 * the UI must be able to tell the two apart. usePolling is the single
 * shared data-fetching layer behind both the dashboard stats and the
 * Business Command Centre panel, so the classification belongs here.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";

describe("usePolling — classifies auth errors separately from other failures", () => {
  it("sets isAuthError=true when the fetcher rejects with a 401 ApiError", async () => {
    const fetcher = vi.fn(() => Promise.reject(new ApiError("Request to /dashboard failed with 401", 401)));

    const { result } = renderHook(() => usePolling(fetcher, { intervalMs: 60_000 }));

    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.isAuthError).toBe(true);
  });

  it("sets isAuthError=true for a 403 ApiError too", async () => {
    const fetcher = vi.fn(() => Promise.reject(new ApiError("Request to /dashboard failed with 403", 403)));

    const { result } = renderHook(() => usePolling(fetcher, { intervalMs: 60_000 }));

    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.isAuthError).toBe(true);
  });

  it("leaves isAuthError=false for a network failure (status 0)", async () => {
    const fetcher = vi.fn(() => Promise.reject(new ApiError("Could not reach the API at /dashboard", 0)));

    const { result } = renderHook(() => usePolling(fetcher, { intervalMs: 60_000 }));

    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.isAuthError).toBe(false);
  });

  it("leaves isAuthError=false for a 500 ApiError", async () => {
    const fetcher = vi.fn(() => Promise.reject(new ApiError("Request to /dashboard failed with 500", 500)));

    const { result } = renderHook(() => usePolling(fetcher, { intervalMs: 60_000 }));

    await waitFor(() => expect(result.current.status).toBe("error"));

    expect(result.current.isAuthError).toBe(false);
  });

  it("resets isAuthError back to false once a subsequent fetch succeeds", async () => {
    // enabled: false so only the explicit refetch() calls below drive
    // fetching — no interval tick can race with them.
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new ApiError("Request to /dashboard failed with 401", 401))
      .mockResolvedValueOnce({ ok: true });

    const { result } = renderHook(() => usePolling(fetcher, { enabled: false }));

    await act(async () => {
      await result.current.refetch();
    });
    expect(result.current.isAuthError).toBe(true);

    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.isAuthError).toBe(false);
    expect(result.current.status).toBe("success");
  });
});
