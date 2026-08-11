"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP, formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";
import type { Quote } from "@/types/quote";

export default function QuoteDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getQuote(params.id)
      .then((q) => {
        setQuote(q);
        if (q.customer_id) {
          api.getCustomer(q.customer_id).then(setCustomer).catch(() => {});
        }
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Quote not found."
            : "Something went wrong."
        )
      );
  }, [isReady, isAuthenticated, router, params.id]);

  if (!isReady || !isAuthenticated) return null;

  async function handleDownload() {
    if (!quote) return;
    setDownloading(true);
    try {
      await api.downloadInvoice(quote.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download the invoice.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <Link href="/quotes" className="text-sm text-muted hover:text-foreground">
          &larr; Quotes
        </Link>
      </div>

      {error && (
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {!error && !quote && <p className="text-sm text-muted">Loading…</p>}

      {quote && (
        <Card>
          <CardContent>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-foreground">
                  {quote.material} ({quote.thickness})
                </h1>
                <p className="text-xs text-muted">
                  Calculated {formatRelativeTime(quote.created_at)}
                </p>
              </div>
              <span className="text-lg font-semibold text-foreground">
                {formatCurrencyGBP(quote.total)}
              </span>
            </div>

            <dl className="mt-6 space-y-3 border-t border-border pt-4">
              <div>
                <dt className="text-xs font-medium text-muted">Customer</dt>
                <dd className="text-sm text-foreground">
                  {customer ? (
                    <Link
                      href={`/customers/${customer.id}`}
                      className="text-accent hover:underline"
                    >
                      {customer.name}
                    </Link>
                  ) : (
                    "No customer linked"
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted">Kitchen run length</dt>
                <dd className="text-sm text-foreground">{quote.kitchen_length}m</dd>
              </div>
              <div className="grid grid-cols-2 gap-y-1">
                <dt className="text-xs text-muted">Price per slab</dt>
                <dd className="text-right text-sm text-foreground">
                  {formatCurrencyGBP(quote.price_per_slab)}
                </dd>
                <dt className="text-xs text-muted">Subtotal</dt>
                <dd className="text-right text-sm text-foreground">
                  {formatCurrencyGBP(quote.price_before_vat)}
                </dd>
                <dt className="text-xs text-muted">VAT (20%)</dt>
                <dd className="text-right text-sm text-foreground">
                  {formatCurrencyGBP(quote.vat)}
                </dd>
                <dt className="text-xs font-semibold text-foreground">Total</dt>
                <dd className="text-right text-sm font-semibold text-foreground">
                  {formatCurrencyGBP(quote.total)}
                </dd>
              </div>
            </dl>

            <div className="mt-6 border-t border-border pt-4">
              <Button onClick={handleDownload} disabled={downloading} variant="outline">
                {downloading ? "Downloading…" : "Download Invoice"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
