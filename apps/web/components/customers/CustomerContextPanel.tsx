"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { api } from "@/lib/api";
import { stageTone } from "@/lib/projects";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { CustomerContext } from "@/types/customer";
import { QUOTE_STATUS_LABELS, type QuoteStatus } from "@/types/quote";

const QUOTE_TONE: Record<QuoteStatus, "neutral" | "info" | "success"> = {
  draft: "neutral",
  sent: "info",
  approved: "success",
};

/**
 * Customer detail business context — Sprint 036, Workstream D.
 *
 * The customer page used to show three fields. This is the part that
 * makes it useful: what this customer has been quoted, what they have
 * agreed to, and what work is running for them — in one call
 * (GET /customers/{id}/context) so the page has no partially-loaded
 * intermediate state.
 *
 * "Quoted" and "Approved" are labelled as amounts quoted and agreed, not
 * as revenue. That is the same distinction the backend has drawn since
 * Sprint 025, and it is worth repeating in the UI because this is exactly
 * where someone would otherwise read it as income.
 */
export function CustomerContextPanel({ customerId }: { customerId: string }) {
  const [context, setContext] = useState<CustomerContext | null>(null);
  const [error, setError] = useState(false);
  const { currency } = useWorkspace();

  useEffect(() => {
    api
      .getCustomerContext(customerId)
      .then(setContext)
      .catch(() => setError(true));
  }, [customerId]);

  if (error) {
    return (
      <Card className="mt-6">
        <CardContent>
          <p className="text-sm text-danger">Could not load this customer&rsquo;s history.</p>
        </CardContent>
      </Card>
    );
  }

  if (!context) {
    return (
      <Card className="mt-6">
        <CardContent className="space-y-2">
          <div className="h-16 animate-pulse rounded-lg bg-surface-hover" />
          <div className="h-24 animate-pulse rounded-lg bg-surface-hover" />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs font-medium text-muted">Quoted</p>
          <p className="mt-1 text-xl font-semibold text-foreground">
            {formatCurrency(context.quoted_value, currency)}
          </p>
          <p className="mt-0.5 text-xs text-muted">Across {context.quotes.length} quote{context.quotes.length === 1 ? "" : "s"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium text-muted">Agreed</p>
          <p className="mt-1 text-xl font-semibold text-foreground">
            {formatCurrency(context.approved_value, currency)}
          </p>
          <p className="mt-0.5 text-xs text-muted">Approved quotes</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs font-medium text-muted">Live jobs</p>
          <p className="mt-1 text-xl font-semibold text-foreground">
            {context.open_projects}
          </p>
          <p className="mt-0.5 text-xs text-muted">Not yet complete</p>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Quotes</CardTitle>
          <Link
            href={`/quotes/new?customer=${customerId}`}
            className="tap-link text-xs font-medium text-accent hover:underline"
          >
            New quote
          </Link>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          {context.quotes.length === 0 ? (
            <EmptyState
              title="No quotes yet"
              description="Quote this customer and it will appear here with its status and value."
              action={
                <Link href={`/quotes/new?customer=${customerId}`}>
                  <Button variant="outline" size="sm">
                    Create a quote
                  </Button>
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {context.quotes.map((quote) => (
                <li key={quote.id}>
                  <Link
                    href={`/quotes/${quote.id}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-surface-hover"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {quote.title ?? "Worktop quote"}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {formatDate(quote.created_at)}
                        {quote.valid_until ? ` · valid until ${formatDate(quote.valid_until)}` : ""}
                      </p>
                    </div>
                    <span className="shrink-0 text-sm font-medium text-foreground">
                      {quote.total === null
                        ? "—"
                        : formatCurrency(quote.total, quote.currency)}
                    </span>
                    <Badge tone={QUOTE_TONE[quote.status as QuoteStatus] ?? "neutral"}>
                      {QUOTE_STATUS_LABELS[quote.status as QuoteStatus] ?? quote.status}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="mt-6">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Projects</CardTitle>
          <Link
            href={`/projects/new?customer=${customerId}`}
            className="tap-link text-xs font-medium text-accent hover:underline"
          >
            New project
          </Link>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          {context.projects.length === 0 ? (
            <EmptyState
              title="No projects yet"
              description="Approving a quote and handing it off creates the project automatically."
            />
          ) : (
            <ul className="divide-y divide-border">
              {context.projects.map((project) => (
                <li key={project.id}>
                  <Link
                    href={`/projects/${project.id}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-surface-hover"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {project.name}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {project.start_date
                          ? `Starts ${formatDate(project.start_date)}`
                          : `Added ${formatDate(project.created_at)}`}
                      </p>
                    </div>
                    <Badge tone={stageTone(project.status_role)}>
                      {project.status_label ?? project.status}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </>
  );
}
