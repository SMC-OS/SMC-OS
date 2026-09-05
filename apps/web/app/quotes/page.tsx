"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, EmptyState } from "@/components/ui/Card";
import { FileTextIcon, LayersIcon, PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { cn, formatCurrency, formatDate, formatRelativeTime } from "@/lib/utils";
import {
  QUOTE_STATUS_LABELS,
  type Quote,
  type QuoteStatus,
} from "@/types/quote";

const STATUS_TONE: Record<QuoteStatus, "neutral" | "info" | "success"> = {
  draft: "neutral",
  sent: "info",
  approved: "success",
};

const FILTERS = [
  { key: "all", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "sent", label: "Sent" },
  { key: "approved", label: "Approved" },
] as const;

/**
 * Sprint 036 (Workstream E) — one list holding both kinds of quote.
 *
 * A general quote has a job title; a stone quote never did, so it falls
 * back to its material summary. The two are visually distinguished by a
 * badge rather than being split into separate lists: they are the same
 * thing to the person running the business — work they have priced — and
 * splitting them would make "what have I got out?" two questions.
 */
function quoteTitle(quote: Quote): string {
  if (quote.title) return quote.title;
  if (quote.items && quote.items.length > 1) {
    return `${quote.items.length} items — ${quote.material ?? "Worktops"}`;
  }
  if (quote.material) {
    return quote.thickness ? `${quote.material} (${quote.thickness})` : quote.material;
  }
  return "Quote";
}

export default function QuotesPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getQuotes(200)
      .then(setQuotes)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [isReady, isAuthenticated, router]);

  const filtered = useMemo(() => {
    if (!quotes) return null;
    if (filter === "all") return quotes;
    return quotes.filter((quote) => quote.status === filter);
  }, [quotes, filter]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Quotes
          </h1>
          <p className="mt-1 text-sm text-muted">
            Every job you have priced — building, renovation, worktops and everything else.
          </p>
        </div>
        <Link href="/quotes/new">
          <Button size="lg">
            <PlusIcon className="h-4 w-4" />
            New quote
          </Button>
        </Link>
      </div>

      {quotes && quotes.length > 0 && (
        <div
          role="tablist"
          aria-label="Filter quotes by status"
          className="mb-4 flex gap-2 overflow-x-auto pb-1"
        >
          {FILTERS.map((option) => (
            <button
              key={option.key}
              type="button"
              role="tab"
              aria-selected={filter === option.key}
              onClick={() => setFilter(option.key)}
              className={cn(
                "shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                filter === option.key
                  ? "border-accent bg-accent text-accent-foreground"
                  : "border-border text-muted hover:border-border-strong hover:text-foreground"
              )}
            >
              {option.label}
              {option.key !== "all" && (
                <span className="ml-1.5 opacity-70">
                  {quotes.filter((quote) => quote.status === option.key).length}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {error && <p className="p-5 text-sm text-danger">{error}</p>}

          {!error && quotes === null && (
            <div className="space-y-2 p-5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-hover" />
              ))}
            </div>
          )}

          {!error && quotes?.length === 0 && (
            <EmptyState
              title="No quotes yet"
              description="Price a job line by line, or use the stone template to price worktops from your material catalogue."
              action={
                <Link href="/quotes/new">
                  <Button>Create your first quote</Button>
                </Link>
              }
            />
          )}

          {filtered?.length === 0 && quotes && quotes.length > 0 && (
            <EmptyState title={`No ${filter} quotes`} />
          )}

          {filtered && filtered.length > 0 && (
            <ul className="divide-y divide-border">
              {filtered.map((quote) => (
                <li key={quote.id}>
                  <Link
                    href={`/quotes/${quote.id}`}
                    className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-hover sm:px-5"
                  >
                    <div
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                        quote.quote_kind === "stone"
                          ? "bg-champagne-subtle text-champagne"
                          : "bg-accent-subtle text-accent"
                      )}
                    >
                      {quote.quote_kind === "stone" ? (
                        <LayersIcon className="h-4 w-4" />
                      ) : (
                        <FileTextIcon className="h-4 w-4" />
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {quoteTitle(quote)}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {quote.valid_until
                          ? `Valid until ${formatDate(quote.valid_until)}`
                          : formatRelativeTime(quote.created_at)}
                      </p>
                    </div>

                    <span className="shrink-0 text-sm font-medium text-foreground">
                      {formatCurrency(quote.total ?? 0, quote.currency)}
                    </span>

                    <Badge tone={STATUS_TONE[quote.status] ?? "neutral"}>
                      {QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
