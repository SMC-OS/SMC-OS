"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import type { AppNotification } from "@/types/notification";
import { usePolling } from "@/hooks/usePolling";

const POLL_INTERVAL_MS = 5000;

export function useNotifications(limit = 20) {
  const fetcher = useCallback(() => api.getNotifications(limit), [limit]);
  const { data, status, error, refetch } = usePolling<AppNotification[]>(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
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
