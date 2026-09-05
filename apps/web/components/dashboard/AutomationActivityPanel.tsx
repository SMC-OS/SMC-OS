"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { AutomationRun } from "@/types/automation";

const STATUS_TONE = {
  succeeded: "success",
  failed: "danger",
  skipped: "neutral",
} as const;

/**
 * Automation activity — Sprint 036 (Workstream C/G).
 *
 * Failures are shown, not hidden. A rule that quietly stopped working is
 * the failure mode this whole feature has to defend against, so the
 * dashboard surfaces failed runs rather than only successes, and the
 * empty state offers the templates that would populate it.
 */
export function AutomationActivityPanel() {
  const [runs, setRuns] = useState<AutomationRun[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .getAutomationRuns(undefined, 5)
      .then(setRuns)
      .catch(() => setError(true));
  }, []);

  const failures = (runs ?? []).filter((run) => run.status === "failed").length;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Automation activity</CardTitle>
        {failures > 0 ? (
          <Badge tone="danger">
            {failures} failed
          </Badge>
        ) : (
          <Link href="/automations" className="text-xs font-medium text-accent hover:underline">
            Manage
          </Link>
        )}
      </CardHeader>

      <CardContent className="p-0 pt-2">
        {error && (
          <p className="px-5 py-4 text-sm text-danger">Could not load automation activity.</p>
        )}

        {!error && runs === null && (
          <div className="space-y-2 p-5">
            {[0, 1].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded-lg bg-surface-hover" />
            ))}
          </div>
        )}

        {!error && runs?.length === 0 && (
          <EmptyState
            title="No automations have run yet"
            description="Turn on a template — chase unanswered quotes, or turn an approved quote into a project automatically."
            action={
              <Link href="/automations">
                <Button variant="outline" size="sm">
                  Browse templates
                </Button>
              </Link>
            }
          />
        )}

        {runs && runs.length > 0 && (
          <ul className="divide-y divide-border">
            {runs.map((run) => (
              <li key={run.id} className="flex items-start gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-foreground">
                    {run.detail ?? run.trigger_type}
                  </p>
                  <p className="text-xs text-muted">
                    {run.trigger_type} · {formatRelativeTime(run.created_at)}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[run.status]}>{run.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
