"use client";

import { api } from "@/lib/api";
import type { DashboardStats } from "@/types/dashboard";
import { usePolling } from "@/hooks/usePolling";

const POLL_INTERVAL_MS = 5000;

export function useDashboardStats() {
  return usePolling<DashboardStats>(api.getDashboardStats, {
    intervalMs: POLL_INTERVAL_MS,
  });
}
