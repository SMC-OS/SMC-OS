"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useActivity } from "@/hooks/useActivity";
import { ACTIVITY_ICON, ACTIVITY_TONE } from "@/lib/activity";
import { formatRelativeTime } from "@/lib/utils";

export function RecentActivityPanel() {
  const { data, status } = useActivity(8);
  const events = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Activity</CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        {status === "loading" && events.length === 0 && (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-surface-hover" />
            ))}
          </div>
        )}

        {status !== "loading" && events.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">No recent activity yet.</p>
        )}

        <ul className="space-y-1">
          {events.map((event) => {
            const EventIcon = ACTIVITY_ICON[event.type];

            return (
              <li key={event.id} className="flex items-start gap-3 rounded-lg px-1 py-2">
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${ACTIVITY_TONE[event.type]}`}
                >
                  <EventIcon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {event.title}
                  </p>
                  {event.description && (
                    <p className="truncate text-xs text-muted">{event.description}</p>
                  )}
                </div>
                <span className="shrink-0 text-xs text-muted">
                  {formatRelativeTime(event.timestamp)}
                </span>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
