"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import { getToken } from "@/lib/auth-storage";
import type { AppNotification } from "@/types/notification";
import { usePolling } from "@/hooks/usePolling";

const POLL_INTERVAL_MS = 5000;

export function useNotifications(limit = 20) {
  // AppShell renders the notifications bell on every route, including
  // ones nobody is signed in on (login, signup, reset-password, the
  // Demo Workspace) — this must never poll a real tenant's API without
  // a session to scope it to. Reading the token directly (rather than
  // useAuth()) avoids a dependency on AuthProvider's own async readiness
  // delay — there's a session to call the API with, or there isn't.
  const fetcher = useCallback(() => api.getNotifications(limit), [limit]);
  const { data, status, error, refetch } = usePolling<AppNotification[]>(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
    enabled: getToken() !== null,
  });

  const [pendingReadIds, setPendingReadIds] = useState<Set<string>>(new Set());

  const markRead = useCallback(
    async (id: string) => {
      setPendingReadIds((prev) => new Set(prev).add(id));
      try {
        await api.markNotificationRead(id);
        await refetch();
      } finally {
        setPendingReadIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [refetch]
  );

  const unreadCount = (data ?? []).filter((n) => !n.read).length;

  return { notifications: data ?? [], status, error, unreadCount, markRead, pendingReadIds };
}
