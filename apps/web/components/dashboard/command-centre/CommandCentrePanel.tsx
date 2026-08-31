"use client";

import Link from "next/link";

import { AlertCircleIcon } from "@/components/ui/icons";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useCommandCentre } from "@/hooks/useCommandCentre";
import { PROJECT_STATUS_LABEL } from "@/lib/projects";
import { formatCurrencyGBP } from "@/lib/utils";
import type { ProjectStatus } from "@/types/project";

// The exact 7-value pipeline order this UI renders in — mirrors the
// backend's PipelineCounts field order (docs/SPRINTS/sprint-025.md §3).
const PIPELINE_ORDER: ProjectStatus[] = [
  "enquiry",
  "quoted",
  "booked",
  "templated",
  "fabricated",
  "installed",
  "complete",
];

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
  const { data, status, error } = useCommandCentre();
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
            <Link href="/projects" className="text-xs font-medium text-accent hover:underline">
              View projects
            </Link>
          </CardHeader>
          <CardContent>
            {PIPELINE_ORDER.map((statusKey) => (
              <CountRow
                key={statusKey}
                label={PROJECT_STATUS_LABEL[statusKey]}
                value={data.pipeline[statusKey]}
              />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Quote Funnel</CardTitle>
            <Link href="/quotes" className="text-xs font-medium text-accent hover:underline">
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
