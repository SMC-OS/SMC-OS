"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { GeneralQuoteBuilder } from "@/components/quotes/GeneralQuoteBuilder";
import { Card, CardContent } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import type { Quote } from "@/types/quote";

/**
 * Edit an existing quote — Sprint 039 Production Readiness Defect Gate,
 * Blocker 5.
 *
 * The backend's PATCH /quotes/{id} and the frontend's `updateGeneralQuote`
 * API client both already existed and were already fully tested; nothing
 * in the UI ever called either. This page is that missing entry point,
 * built on the same `GeneralQuoteBuilder` the "new quote" flow uses, so a
 * quote's price is always computed by the one piece of code that knows
 * how — not a second, divergent copy of the arithmetic.
 *
 * Only a draft general quote can be edited (see
 * app/quotes/service.py's QuoteService.update_general for the exact
 * refusals this mirrors): a stone quote is priced by a different code
 * path, and a sent or approved quote is a document someone else already
 * holds. Both cases are told to the user plainly rather than rendering a
 * form that would just fail on submit.
 */
export default function EditQuotePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useAuth();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getQuote(params.id)
      .then(setQuote)
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Quote not found."
            : "Something went wrong."
        )
      );
  }, [isReady, isAuthenticated, router, params.id]);

  if (!isReady || !isAuthenticated) return null;

  const canAct = role === "Owner" || role === "Staff";

  function refusal(message: string) {
    return (
      <div className="mx-auto max-w-3xl">
        <div className="mb-6">
          <Link
            href={`/quotes/${params.id}`}
            className="tap-link text-sm text-muted hover:text-foreground"
          >
            &larr; Quote
          </Link>
        </div>
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{message}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) return refusal(error);
  if (!quote) return <p className="text-sm text-muted">Loading…</p>;
  if (!canAct) return refusal("Only workspace owners and staff can edit a quote.");
  if (quote.quote_kind !== "general") {
    return refusal("Only general quotes can be edited here — stone quotes use their own template.");
  }
  if (quote.status !== "draft") {
    return refusal("Only draft quotes can be edited — this one has already been sent or approved.");
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <Link
          href={`/quotes/${quote.id}`}
          className="tap-link text-sm text-muted hover:text-foreground"
        >
          &larr; Quote
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Edit quote
        </h1>
        <p className="mt-1 text-sm text-muted">
          Changes are saved to this quote — it stays the same document, just updated.
        </p>
      </div>

      <GeneralQuoteBuilder existingQuote={quote} />
    </div>
  );
}
