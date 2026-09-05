"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, todayISO, daysFromTodayISO } from "@/lib/utils";
import type { CalendarItem } from "@/types/calendar";

const TYPE_LABEL: Record<string, string> = {
  project_start: "Starts",
  project_target_completion: "Due",
  site_visit: "Site visit",
  task_due: "Task",
  quote_expiry: "Quote expires",
};

/**
 * Upcoming work — Sprint 036 (Workstream C/K).
 *
 * Reads the same calendar feed the Calendar page does, over the next two
 * weeks. Every item is a real dated row this workspace owns; nothing is
 * predicted. An all-day item renders as a date, a timed one as a date and
 * time, because rendering a project start at "00:00" is wrong in a way
 * that erodes trust in the whole panel.
 */
export function UpcomingPanel() {
  const [items, setItems] = useState<CalendarItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getCalendar(todayISO(), daysFromTodayISO(14))
      .then((response) => setItems(response.items.slice(0, 6)))
      .catch(() => setError(true));
  }, []);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Next two weeks</CardTitle>
        <Link href="/calendar" className="tap-link text-xs font-medium text-accent hover:underline">
          Calendar
        </Link>
      </CardHeader>

      <CardContent className="p-0 pt-2">
        {error && (
          <p className="px-5 py-4 text-sm text-danger">Could not load your calendar.</p>
        )}

        {!error && items === null && (
          <div className="space-y-2 p-5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-surface-hover" />
            ))}
          </div>
        )}

        {!error && items?.length === 0 && (
          <EmptyState
            title="Nothing scheduled"
            description="Project start dates, target completions, site visits and task deadlines all show up here."
            action={
              <Link href="/projects/new">
                <Button variant="outline" size="sm">
                  Add a project
                </Button>
              </Link>
            }
          />
        )}

        {items && items.length > 0 && (
          <ul className="divide-y divide-border">
            {items.map((item) => (
              <li key={item.id} className="flex items-start gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {item.title}
                  </p>
                  <p className="truncate text-xs text-muted">
                    {TYPE_LABEL[item.type] ?? "Scheduled"} ·{" "}
                    {item.all_day ? formatDate(item.at) : formatDateTime(item.at)}
                    {item.subtitle ? ` · ${item.subtitle}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
