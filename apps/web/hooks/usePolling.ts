"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type FetchStatus = "loading" | "success" | "error";

interface UsePollingOptions {
  intervalMs?: number;
  enabled?: boolean;
}

interface UsePollingResult<T> {
  data: T | null;
  status: FetchStatus;
  error: string | null;
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
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;

    load();
    const id = setInterval(load, intervalMs);
    return () => clearInterval(id);
  }, [enabled, intervalMs, load]);

  return { data, status, error, refetch: load };
}
