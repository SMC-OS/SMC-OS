"use client";

import Link from "next/link";

import { AlertCircleIcon } from "@/components/ui/icons";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useCommandCentre } from "@/hooks/useCommandCentre";
import { formatCurrencyGBP } from "@/lib/utils";
import { WORKFLOW_ROLES, WORKFLOW_ROLE_LABELS } from "@/types/workflow";

// GeoCore Premium OS Plan 01 (Sprint 040, Task 9) — the Pipeline card
// aggregates by the 13 shared semantic roles (app/dashboard/models.py's
// PipelineRoleCounts), not the old 7-value stone-shaped ProjectStatus
// pipeline: a stone project on "Fabrication" and an electrical one on
// "First Fix" now count together under one company-wide "In Progress"
// row instead of needing a trade-specific row each. Every role always
// renders, 0 if none — same never-sparse contract the backend itself
// guarantees.

function SectionSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="h-4 w-32 animate-pulse rounded bg-surface-hover" />
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="h-4 w-full animate-pulse rounded bg-surface-hover" />
        <div className="h-4 w-full animate-pulse rounded bg-surface-hover" />
        <div className="h-4 w-2/3 animate-pulse rounded bg-surface-hover" />
      </CardContent>
    </Card>
  );
}

function CountRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-foreground">{value.toLocaleString("en-GB")}</span>
    </div>
  );
}

export function CommandCentrePanel() {
  const { data, status, error, isAuthError } = useCommandCentre();
  const loading = status === "loading" && !data;

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionSkeleton />
        <SectionSkeleton />
        <SectionSkeleton />
        <SectionSkeleton />
      </div>
    );
  }

  if (status === "error" && !data && isAuthError) {
    // Production incident (post-v1.0.1): a 401/403 must never be reported
    // as a failure to load the Command Centre — that's an availability
    // message for a session problem. app/page.tsx's own auth guard
    // redirects to /login as soon as the session is known invalid; this is
    // only what briefly shows first.
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-6 text-sm text-warning">
          <AlertCircleIcon className="h-4 w-4 shrink-0" />
          Your session has expired.
        </CardContent>
      </Card>
    );
  }

  if (status === "error" && !data) {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 py-6 text-sm text-danger">
          <AlertCircleIcon className="h-4 w-4 shrink-0" />
          Couldn&rsquo;t load the Business Command Centre{error ? ` (${error})` : ""}.
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold tracking-tight text-foreground">
        Business Command Centre
      </h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Pipeline</CardTitle>
            <Link href="/projects" className="tap-link text-xs font-medium text-accent hover:underline">
              View projects
            </Link>
          </CardHeader>
          <CardContent>
            {WORKFLOW_ROLES.map((role) => (
              <CountRow
                key={role}
                label={WORKFLOW_ROLE_LABELS[role]}
                value={data.pipeline_by_role[role]}
              />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Quote Funnel</CardTitle>
            <Link href="/quotes" className="tap-link text-xs font-medium text-accent hover:underline">
              View quotes
            </Link>
          </CardHeader>
          <CardContent>
            <CountRow label="Draft" value={data.quotes.draft} />
            <CountRow label="Approved" value={data.quotes.approved} />
            <CountRow label="Handed off" value={data.quotes.handed_off} />
            <div className="mt-3 border-t border-border pt-3">
              <CountRowValue label="Quoted value" value={data.value.quoted_value} />
              <CountRowValue
                label="Approved quote value"
                value={data.value.approved_quoted_value}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Site Visits</CardTitle>
          </CardHeader>
          <CardContent>
            <CountRow label="Scheduled" value={data.site_visits.scheduled} />
            <CountRow label="Completed" value={data.site_visits.completed} />
            <CountRow label="Cancelled" value={data.site_visits.cancelled} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Follow-up Attention</CardTitle>
            {data.follow_up.unread_follow_ups > 0 && (
              <Badge tone="warning">{data.follow_up.unread_follow_ups} unread</Badge>
            )}
          </CardHeader>
          <CardContent>
            <CountRow label="Unread follow-ups" value={data.follow_up.unread_follow_ups} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CountRowValue({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-1 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-foreground">{formatCurrencyGBP(value)}</span>
    </div>
  );
}
