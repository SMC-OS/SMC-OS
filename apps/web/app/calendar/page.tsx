"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, EmptyState } from "@/components/ui/Card";
import {
  CalendarIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClipboardIcon,
  ClockIcon,
  FileTextIcon,
  FolderIcon,
} from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { cn, formatDate, formatDateTime } from "@/lib/utils";
import type { CalendarItem, CalendarItemType } from "@/types/calendar";

const TYPE_META: Record<
  CalendarItemType,
  { label: string; tone: "accent" | "info" | "warning" | "neutral"; icon: typeof CalendarIcon }
> = {
  project_start: { label: "Project starts", tone: "accent", icon: FolderIcon },
  project_target_completion: { label: "Target completion", tone: "info", icon: FolderIcon },
  site_visit: { label: "Site visit", tone: "info", icon: CalendarIcon },
  task_due: { label: "Task due", tone: "neutral", icon: ClipboardIcon },
  quote_expiry: { label: "Quote expires", tone: "warning", icon: FileTextIcon },
};

function isoDate(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function endOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

/**
 * Calendar — Sprint 036, Workstream K.
 *
 * An agenda grouped by day, not a month grid. A month grid looks like a
 * calendar and is close to useless on a phone, which is where a builder
 * actually checks what is on tomorrow; an agenda reads the same at 360px
 * and at 1440px, and shows what each item actually is rather than a dot.
 *
 * Every item here is a real dated row this workspace owns — project start
 * and target dates, scheduled site visits, task due dates and quote
 * expiries. There is deliberately no "connect Google Calendar" or ICS
 * export, because GeoCore has no external calendar integration and an
 * affordance implying one would be a claim it cannot honour.
 */
export default function CalendarPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();

  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const [items, setItems] = useState<CalendarItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The fetch lives inside the effect and every state write happens in a
  // promise callback. The month is tracked separately from the loaded
  // items so switching month can render the previous month's agenda
  // (rather than a flash of nothing) until the new one arrives, without
  // a synchronous setState in the effect body.
  const [loadedMonth, setLoadedMonth] = useState<string | null>(null);
  const monthKey = isoDate(month).slice(0, 7);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }

    let cancelled = false;
    api
      .getCalendar(isoDate(startOfMonth(month)), isoDate(endOfMonth(month)))
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
        setLoadedMonth(monthKey);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Something went wrong.");
        setLoadedMonth(monthKey);
      });

    return () => {
      cancelled = true;
    };
  }, [isReady, isAuthenticated, router, month, monthKey]);

  const loading = loadedMonth !== monthKey;

  const grouped = useMemo(() => {
    if (!items || loading) return null;
    const byDay = new Map<string, CalendarItem[]>();
    for (const item of items) {
      const day = item.at.slice(0, 10);
      byDay.set(day, [...(byDay.get(day) ?? []), item]);
    }
    return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [items, loading]);

  if (!isReady || !isAuthenticated) return null;

  const today = isoDate(new Date());

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Calendar
        </h1>
        <p className="mt-1 text-sm text-muted">
          Start dates, target completions, site visits, task deadlines and quote
          expiries — everything dated in your workspace.
        </p>
      </div>

      <div className="mb-4 flex items-center justify-between gap-3">
        <Button
          variant="outline"
          size="sm"
          aria-label="Previous month"
          onClick={() => setMonth((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}
        >
          <ChevronLeftIcon className="h-4 w-4" />
          <span className="hidden sm:inline">Previous</span>
        </Button>

        <p className="text-sm font-semibold text-foreground">
          {month.toLocaleDateString("en-GB", { month: "long", year: "numeric" })}
        </p>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMonth(startOfMonth(new Date()))}
          >
            Today
          </Button>
          <Button
            variant="outline"
            size="sm"
            aria-label="Next month"
            onClick={() => setMonth((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}
          >
            <span className="hidden sm:inline">Next</span>
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>
      )}

      {loading && !error && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-2xl bg-surface-hover" />
          ))}
        </div>
      )}

      {grouped?.length === 0 && (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              title="Nothing scheduled this month"
              description="Give a project a start date, book a site visit, or set a due date on a task and it will show up here."
              action={
                <Link href="/projects">
                  <Button variant="outline" size="sm">
                    Go to projects
                  </Button>
                </Link>
              }
            />
          </CardContent>
        </Card>
      )}

      {grouped && grouped.length > 0 && (
        <div className="space-y-4">
          {grouped.map(([day, dayItems]) => (
            <Card key={day}>
              <CardContent className="p-0">
                <div
                  className={cn(
                    "flex items-center gap-2 border-b border-border px-5 py-3",
                    day === today && "bg-accent-subtle"
                  )}
                >
                  <p className="text-sm font-semibold text-foreground">
                    {formatDate(day)}
                  </p>
                  {day === today && <Badge tone="accent">Today</Badge>}
                </div>

                <ul className="divide-y divide-border">
                  {dayItems.map((item) => {
                    const meta = TYPE_META[item.type];
                    const ItemIcon = meta?.icon ?? CalendarIcon;
                    const href =
                      item.source_type === "project"
                        ? `/projects/${item.source_id}`
                        : item.source_type === "quote"
                          ? `/quotes/${item.source_id}`
                          : null;

                    const content = (
                      <div className="flex items-start gap-3 px-5 py-3">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-hover text-muted">
                          <ItemIcon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground">
                            {item.title}
                          </p>
                          <p className="flex items-center gap-1.5 truncate text-xs text-muted">
                            {!item.all_day && (
                              <>
                                <ClockIcon className="h-3.5 w-3.5 shrink-0" />
                                {formatDateTime(item.at).split(", ").pop()}
                              </>
                            )}
                            {meta?.label ?? "Scheduled"}
                            {item.subtitle ? ` · ${item.subtitle}` : ""}
                          </p>
                        </div>
                        <Badge tone={meta?.tone ?? "neutral"} className="hidden sm:inline-flex">
                          {meta?.label ?? "Scheduled"}
                        </Badge>
                      </div>
                    );

                    return (
                      <li key={item.id}>
                        {href ? (
                          <Link href={href} className="block transition-colors hover:bg-surface-hover">
                            {content}
                          </Link>
                        ) : (
                          content
                        )}
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
