"use client";

import { useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  BellIcon,
  CheckCircleIcon,
  InfoIcon,
} from "@/components/ui/icons";
import { useClickOutside } from "@/hooks/useClickOutside";
import { useNotifications } from "@/hooks/useNotifications";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { NotificationType } from "@/types/notification";

const TYPE_ICON: Record<NotificationType, typeof CheckCircleIcon> = {
  success: CheckCircleIcon,
  warning: AlertTriangleIcon,
  info: InfoIcon,
  error: AlertCircleIcon,
};

const TYPE_TONE: Record<NotificationType, string> = {
  success: "text-success",
  warning: "text-warning",
  info: "text-info",
  error: "text-danger",
};

export function NotificationsPanel() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false));

  const { notifications, unreadCount, markRead, pendingReadIds, status } =
    useNotifications();

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-muted hover:bg-surface-hover hover:text-foreground"
        aria-label="Notifications"
      >
        <BellIcon className="h-[18px] w-[18px]" />
        {unreadCount > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-border bg-surface shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <p className="text-sm font-semibold text-foreground">Notifications</p>
            {unreadCount > 0 && <Badge tone="info">{unreadCount} unread</Badge>}
          </div>

          <div className="max-h-80 overflow-y-auto">
            {status === "loading" && notifications.length === 0 && (
              <p className="px-4 py-6 text-center text-sm text-muted">Loading…</p>
            )}

            {status !== "loading" && notifications.length === 0 && (
              <p className="px-4 py-6 text-center text-sm text-muted">
                You&rsquo;re all caught up.
              </p>
            )}

            {notifications.map((notification) => {
              const TypeIcon = TYPE_ICON[notification.type];
              const isPending = pendingReadIds.has(notification.id);

              return (
                <button
                  key={notification.id}
                  type="button"
                  disabled={notification.read || isPending}
                  onClick={() => markRead(notification.id)}
                  className={cn(
                    "flex w-full items-start gap-3 border-b border-border px-4 py-3 text-left last:border-b-0 hover:bg-surface-hover disabled:cursor-default",
                    !notification.read && "bg-accent/5"
                  )}
                >
                  <TypeIcon
                    className={cn("mt-0.5 h-4 w-4 shrink-0", TYPE_TONE[notification.type])}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-foreground">
                        {notification.title}
                      </span>
                      {!notification.read && (
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {notification.message}
                    </span>
                    <span className="mt-1 block text-[11px] text-muted">
                      {formatRelativeTime(notification.timestamp)}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
