"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/components/auth/AuthProvider";
import type { AppNotification } from "@/types/notification";
import { usePolling } from "@/hooks/usePolling";

const POLL_INTERVAL_MS = 5000;

export function useNotifications(limit = 20) {
  // HttpOnly sessions have no JavaScript bearer token. Poll only after
  // AuthProvider has confirmed the session with the server.
  const { isReady, isAuthenticated } = useAuth();
  const fetcher = useCallback(() => api.getNotifications(limit), [limit]);
  const { data, status, error, refetch } = usePolling<AppNotification[]>(fetcher, {
    intervalMs: POLL_INTERVAL_MS,
    enabled: isReady && isAuthenticated,
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

  const notifications = isReady && isAuthenticated ? data ?? [] : [];
  const unreadCount = notifications.filter((n) => !n.read).length;

  return { notifications, status, error, unreadCount, markRead, pendingReadIds };
}
