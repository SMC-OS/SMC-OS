"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, EmptyState } from "@/components/ui/Card";
import { AlertCircleIcon, MailIcon, RefreshIcon } from "@/components/ui/icons";
import {
  failureGuidance,
  messageTypeLabel,
  relatedEntity,
  STATUS_HINT,
  STATUS_LABEL,
  STATUS_TONE,
} from "@/lib/communications";
import { ApiError, api } from "@/lib/api";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";
import type { Communication, CommunicationFilters } from "@/types/communication";

/**
 * Communication history (Sprint 039, Workstream A).
 *
 * One component behind five screens: the central Communications view, and
 * the timelines on a customer, a quote, a project and the team-invitation
 * list. They differ only by which filter they pass, so they are the same
 * component rather than five that drift apart.
 *
 * What it will not do:
 *
 *   * It never shows a message body. The API does not send one, and a
 *     timeline does not need one.
 *   * It never shows a provider internal — no message ids, no raw error
 *     text. `failure_detail` is sanitised server-side before it is stored.
 *   * It never presents "sent" as "arrived". The provider accepting a
 *     message and the message reaching an inbox are two different facts,
 *     and Sprint 038 went to some trouble to keep them apart; this is
 *     where a user finally sees the difference.
 */

interface Props {
  filters?: CommunicationFilters;
  /** The central view shows more per page than an entity timeline does. */
  limit?: number;
  /** Rendered above the list on entity timelines. */
  title?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  /** Whether to render the surrounding Card. The central page supplies its
   * own layout; entity timelines want the card. */
  bare?: boolean;
}

export function CommunicationTimeline({
  filters,
  limit = 20,
  title,
  emptyTitle = "Nothing sent yet",
  emptyDescription = "Emails GeoCore sends will appear here, with whether they arrived.",
  bare = false,
}: Props) {
  const [rows, setRows] = useState<Communication[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  // Stringified so the effect below depends on the filter's *value* rather
  // than on a new object identity every render.
  const filterKey = JSON.stringify(filters ?? {});

  const load = useCallback(() => {
    // Nothing is set synchronously here: this runs from an effect, and a
    // synchronous setState in an effect triggers a cascading render (the
    // repo's eslint config rejects it). Success clears any previous error
    // at the same moment it supplies the new rows.
    api
      .getCommunications(JSON.parse(filterKey) as CommunicationFilters, limit)
      .then((data) => {
        setRows(data);
        setError(null);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError
            ? "Couldn't load communication history."
            : "Something went wrong."
        )
      );
  }, [filterKey, limit]);

  useEffect(() => {
    load();
  }, [load]);

  async function retry(communication: Communication) {
    setRetryingId(communication.id);
    setError(null);
    try {
      const updated = await api.retryCommunication(communication.id);
      // The server's row is authoritative — never an optimistic "sent".
      setRows((current) =>
        (current ?? []).map((row) => (row.id === updated.id ? updated : row))
      );
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That message can't be retried any more."
          : "Couldn't retry that message."
      );
    } finally {
      setRetryingId(null);
    }
  }

  const body = (
    <>
      {error && (
        <p className="flex items-start gap-2 px-4 py-3 text-sm text-danger sm:px-5">
          <AlertCircleIcon className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </p>
      )}

      {!error && rows === null && (
        <div className="space-y-2 p-4 sm:p-5">
          {[0, 1, 2].map((index) => (
            <div key={index} className="h-16 animate-pulse rounded-lg bg-surface-hover" />
          ))}
        </div>
      )}

      {!error && rows?.length === 0 && (
        <EmptyState title={emptyTitle} description={emptyDescription} />
      )}

      {rows && rows.length > 0 && (
        <ul className="divide-y divide-border">
          {rows.map((row) => (
            <CommunicationRow
              key={row.id}
              communication={row}
              retrying={retryingId === row.id}
              onRetry={() => retry(row)}
            />
          ))}
        </ul>
      )}
    </>
  );

  if (bare) return body;

  return (
    <Card>
      {title && (
        <div className="flex items-center gap-2 border-b border-border px-4 py-3 sm:px-5">
          <MailIcon className="h-4 w-4 text-muted" />
          <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">
            {title}
          </h3>
        </div>
      )}
      <CardContent className="p-0">{body}</CardContent>
    </Card>
  );
}

function CommunicationRow({
  communication,
  retrying,
  onRetry,
}: {
  communication: Communication;
  retrying: boolean;
  onRetry: () => void;
}) {
  const related = relatedEntity(communication);
  const guidance = failureGuidance(communication);
  const hint = STATUS_HINT[communication.status];

  return (
    <li className="px-4 py-3 sm:px-5">
      {/* Stacks on a phone and becomes two columns from `sm` up: the
          subject line is the thing being scanned, and squeezing it next to
          a badge at 390px makes both unreadable. */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {communication.subject}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted">
            {messageTypeLabel(communication.message_type)} · to{" "}
            {communication.recipient}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
            <time dateTime={communication.created_at} title={formatDateTime(communication.created_at)}>
              {formatRelativeTime(communication.created_at)}
            </time>
            {related && (
              <>
                <span aria-hidden="true">·</span>
                <Link href={related.href} className="text-accent hover:underline">
                  {related.label}
                </Link>
              </>
            )}
            {communication.attempt_count > 1 && (
              <>
                <span aria-hidden="true">·</span>
                <span>{communication.attempt_count} attempts</span>
              </>
            )}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[communication.status]}>
            {STATUS_LABEL[communication.status]}
          </Badge>
          {/* A complaint never overwrites the delivery status, so it is
              shown as what it is: an additional fact about a message that
              did arrive. */}
          {communication.complained && (
            <Badge tone="warning" title="This recipient marked the message as spam.">
              Marked as spam
            </Badge>
          )}
          {communication.retryable && (
            <Button size="sm" variant="outline" onClick={onRetry} disabled={retrying}>
              <RefreshIcon className="h-3.5 w-3.5" />
              {retrying ? "Retrying…" : "Try again"}
            </Button>
          )}
        </div>
      </div>

      {(hint || guidance || communication.failure_detail) && (
        <p className="mt-1.5 text-xs text-muted">
          {guidance ?? hint}
          {communication.failure_detail && guidance && (
            <span className="block text-muted/80">{communication.failure_detail}</span>
          )}
        </p>
      )}
    </li>
  );
}
