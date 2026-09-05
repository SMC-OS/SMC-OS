"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { CheckIcon, ClockIcon } from "@/components/ui/icons";
import { api } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import type { Task } from "@/types/task";

/** A task plus whether it was overdue at the moment it was loaded. */
interface OverdueTask extends Task {
  overdue: boolean;
}

/**
 * "What needs my attention" — Sprint 036 (Workstream C).
 *
 * Real open tasks, not a computed score. Tasks come from three genuine
 * sources: someone created one, an automation created one, or an
 * automation drafted a message for a person to send. If there are none,
 * this says so and offers the automations that would create them — an
 * empty state that teaches, rather than a zero pretending to be a
 * measurement.
 */
export function AttentionPanel() {
  const [tasks, setTasks] = useState<OverdueTask[] | null>(null);
  const [error, setError] = useState(false);
  const [completing, setCompleting] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTasks("open", 6)
      // "Overdue" is decided once, when the data arrives, rather than on
      // every render. Reading the clock during render is impure — two
      // renders a second apart could disagree — and a panel listing what
      // needs doing today does not need the clock to tick mid-view.
      .then((loaded) =>
        setTasks(
          loaded.map((task) => ({
            ...task,
            overdue:
              task.due_at !== null &&
              new Date(task.due_at).getTime() < Date.now(),
          }))
        )
      )
      .catch(() => setError(true));
  }, []);

  async function complete(id: string) {
    setCompleting(id);
    try {
      await api.updateTaskStatus(id, "done");
      setTasks((current) => (current ?? []).filter((task) => task.id !== id));
    } catch {
      setError(true);
    } finally {
      setCompleting(null);
    }
  }



  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Needs your attention</CardTitle>
        {tasks && tasks.length > 0 && (
          <Badge tone={tasks.some((task) => task.overdue) ? "warning" : "neutral"}>
            {tasks.length} open
          </Badge>
        )}
      </CardHeader>

      <CardContent className="p-0 pt-2">
        {error && (
          <p className="px-5 py-4 text-sm text-danger">
            Could not load your tasks. Refresh to try again.
          </p>
        )}

        {!error && tasks === null && (
          <div className="space-y-2 p-5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-surface-hover" />
            ))}
          </div>
        )}

        {!error && tasks?.length === 0 && (
          <EmptyState
            title="Nothing waiting on you"
            description="Tasks appear here when you create one, or when an automation creates a follow-up for you."
            action={
              <Link href="/automations">
                <Button variant="outline" size="sm">
                  Set up an automation
                </Button>
              </Link>
            }
          />
        )}

        {tasks && tasks.length > 0 && (
          <ul className="divide-y divide-border">
            {tasks.map((task) => (
              <li key={task.id} className="flex items-start gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">
                    {task.title}
                  </p>
                  {task.due_at && (
                    <p
                      className={cn(
                        "mt-0.5 flex items-center gap-1 text-xs",
                        task.overdue ? "text-warning" : "text-muted"
                      )}
                    >
                      <ClockIcon className="h-3.5 w-3.5 shrink-0" />
                      {task.overdue ? "Overdue — " : "Due "}
                      {formatDateTime(task.due_at)}
                    </p>
                  )}
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  disabled={completing === task.id}
                  onClick={() => complete(task.id)}
                  aria-label={`Mark "${task.title}" as done`}
                >
                  <CheckIcon className="h-4 w-4" />
                  <span className="hidden sm:inline">Done</span>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
