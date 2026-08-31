"use client";

import { api } from "@/lib/api";
import type { CommandCentreStats } from "@/types/command-centre";
import { usePolling } from "@/hooks/usePolling";

const POLL_INTERVAL_MS = 5000;

export function useCommandCentre() {
  return usePolling<CommandCentreStats>(api.getCommandCentre, {
    intervalMs: POLL_INTERVAL_MS,
  });
}
