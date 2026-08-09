"use client";

import { useCallback } from "react";

import { api } from "@/lib/api";
import type { ActivityEvent, ActivityType } from "@/types/activity";
import { usePolling } from "@/hooks/usePolling";

const POLL_INTERVAL_MS = 5000;

export function useActivity(limit = 8, type?: ActivityType) {
  const fetcher = useCallback(() => api.getActivity(limit, type), [limit, type]);

  return usePolling<ActivityEvent[]>(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
  });
}
