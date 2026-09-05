"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { AutomationRun } from "@/types/automation";

const TONE = {
  succeeded: "success",
  failed: "danger",
  skipped: "neutral",
} as const;

/**
 * Run history — Sprint 036, Workstream G.
 *
 * The whole reason this is a first-class panel rather than a log line: an
 * automation that quietly does nothing is indistinguishable from a broken
 * one, and "why didn't my automation fire?" is the question this feature
 * will be asked most. So every attempt is here — succeeded, skipped with
 * its reason, failed with its message.
 */
export function AutomationRunsPanel({ automationId }: { automationId?: string }) {
  const [runs, setRuns] = useState<AutomationRun[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getAutomationRuns(automationId, 25)
      .then(setRuns)
      .catch(() => setError(true));
  }, [automationId]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent runs</CardTitle>
      </CardHeader>
      <CardContent className="p-0 pt-2">
        {error && <p className="px-5 py-4 text-sm text-danger">Could not load run history.</p>}

        {!error && runs === null && (
          <div className="space-y-2 p-5">
            {[0, 1].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-surface-hover" />
            ))}
          </div>
        )}

        {!error && runs?.length === 0 && (
          <EmptyState
            title="Nothing has run yet"
            description="Once an automation is on, every time it fires — or decides not to — shows up here."
          />
        )}

        {runs && runs.length > 0 && (
          <ul className="divide-y divide-border">
            {runs.map((run) => (
              <li key={run.id} className="flex items-start gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{run.detail ?? "—"}</p>
                  <p className="text-xs text-muted">
                    {run.trigger_type} · {formatRelativeTime(run.created_at)}
                  </p>
                </div>
                <Badge tone={TONE[run.status]}>{run.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
