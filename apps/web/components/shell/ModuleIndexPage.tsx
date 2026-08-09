"use client";

import Link from "next/link";

import { ComingSoon } from "@/components/shell/ComingSoon";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { PlusIcon } from "@/components/ui/icons";
import { useActivity } from "@/hooks/useActivity";
import { ACTIVITY_ICON, ACTIVITY_TONE } from "@/lib/activity";
import { formatRelativeTime } from "@/lib/utils";
import type { ActivityType } from "@/types/activity";

export function ModuleIndexPage({
  title,
  description,
  sprint,
  activityType,
  emptyLabel,
  ctaLabel,
  ctaHref,
}: {
  title: string;
  description: string;
  sprint: string;
  activityType: ActivityType;
  emptyLabel: string;
  ctaLabel: string;
  ctaHref: string;
}) {
  const { data } = useActivity(10, activityType);
  const events = data ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {title}
          </h1>
          <p className="mt-1 text-sm text-muted">{description}</p>
        </div>
        <Link href={ctaHref}>
          <Button>
            <PlusIcon className="h-4 w-4" />
            {ctaLabel}
          </Button>
        </Link>
      </div>

      <ComingSoon title={`Full ${title.toLowerCase()} records`} description={description} sprint={sprint} />

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Recently logged</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {events.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted">{emptyLabel}</p>
          ) : (
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
          )}
        </CardContent>
      </Card>
    </div>
  );
}
