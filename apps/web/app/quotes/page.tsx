"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { FileTextIcon, PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP, formatRelativeTime } from "@/lib/utils";
import type { Quote } from "@/types/quote";

export default function QuotesPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [quotes, setQuotes] = useState<Quote[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getQuotes()
      .then(setQuotes)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [isReady, isAuthenticated, router]);

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Quotes
          </h1>
          <p className="mt-1 text-sm text-muted">Every quote calculated to date.</p>
        </div>
        <Link href="/quotes/new">
          <Button>
            <PlusIcon className="h-4 w-4" />
            New Quote
          </Button>
        </Link>
      </div>

      <Card>
        <CardContent className="p-0">
          {error && <p className="p-5 text-sm text-danger">{error}</p>}
          {!error && quotes === null && (
            <p className="p-5 text-center text-sm text-muted">Loading…</p>
          )}
          {!error && quotes?.length === 0 && (
            <p className="p-5 text-center text-sm text-muted">
              No quotes yet — calculate one to see it here.
            </p>
          )}
          {quotes && quotes.length > 0 && (
            <ul className="divide-y divide-border">
              {quotes.map((quote) => (
                <li key={quote.id}>
                  <Link
                    href={`/quotes/${quote.id}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-surface-hover"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
                      <FileTextIcon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {quote.items && quote.items.length > 1
                          ? `${quote.items.length} items — ${quote.material}`
                          : `${quote.material} (${quote.thickness})`}
                      </p>
                    </div>
                    <span className="shrink-0 text-sm font-medium text-foreground">
                      {formatCurrencyGBP(quote.total)}
                    </span>
                    <span className="shrink-0 text-xs text-muted">
                      {formatRelativeTime(quote.created_at)}
                    </span>
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
