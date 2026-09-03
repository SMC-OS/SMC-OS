"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";

export type FetchStatus = "loading" | "success" | "error";

interface UsePollingOptions {
  intervalMs?: number;
  enabled?: boolean;
}

interface UsePollingResult<T> {
  data: T | null;
  status: FetchStatus;
  error: string | null;
  // Production incident (post-v1.0.1): a 401/403 (expired/invalid session)
  // was rendered identically to a real network/API-availability failure.
  // Consumers use this to tell the two apart instead of guessing from the
  // error string.
  isAuthError: boolean;
  refetch: () => Promise<void>;
}

/**
 * Generic polling hook. Fetches immediately, then re-fetches every
 * `intervalMs`. Used by useDashboardStats/useActivity/useNotifications so
 * the polling mechanism can be swapped for a WebSocket subscription later
 * (see docs/architecture) without changing any component that consumes it —
 * only these three hooks would need to change internally.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  { intervalMs = 5000, enabled = true }: UsePollingOptions = {}
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [isAuthError, setIsAuthError] = useState(false);

  // Keep the latest fetcher without re-triggering the effect below.
  // Updated inside its own effect (not during render) so it doesn't mutate
  // a ref while rendering.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const load = useCallback(async () => {
    try {
      const result = await fetcherRef.current();
      setData(result);
      setStatus("success");
      setError(null);
      setIsAuthError(false);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Something went wrong");
      setIsAuthError(err instanceof ApiError && (err.status === 401 || err.status === 403));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    load();
    const id = setInterval(load, intervalMs);
    return () => clearInterval(id);
  }, [enabled, intervalMs, load]);

  return { data, status, error, isAuthError, refetch: load };
}
