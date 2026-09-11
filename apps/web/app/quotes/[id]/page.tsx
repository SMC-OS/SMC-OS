"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { MailIcon, SendIcon } from "@/components/ui/icons";
import { CommunicationTimeline } from "@/components/communications/CommunicationTimeline";
import { MessageComposer } from "@/components/communications/MessageComposer";
import { STATUS_LABEL } from "@/lib/communications";
import { ApiError, api } from "@/lib/api";
import { formatDate, formatMoney, formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";
import {
  ITEM_TYPE_LABELS,
  QUOTE_STATUS_LABELS,
  type Quote,
  type QuoteItem,
  type QuoteStatus,
} from "@/types/quote";

const STATUS_TONE: Record<QuoteStatus, "neutral" | "info" | "success"> = {
  draft: "neutral",
  sent: "info",
  approved: "success",
};

/**
 * Sprint 036 (Workstream E) — one detail page for both kinds of quote.
 *
 * A line describes itself according to its own `line_kind`, not the
 * quote's, so a future quote mixing a worktop with two days of fitting
 * labour renders both correctly with no further change here.
 */
function describeLine(item: QuoteItem): { title: string; detail: string } {
  if (item.line_kind === "stone") {
    const material = item.material
      ? `${item.material}${item.thickness ? ` (${item.thickness})` : ""}`
      : "";
    return {
      title: [ITEM_TYPE_LABELS[item.item_type] ?? item.item_type, material]
        .filter(Boolean)
        .join(" — "),
      detail:
        item.length_mm !== null && item.width_mm !== null
          ? `${item.quantity} × ${item.length_mm}mm × ${item.width_mm}mm`
          : `${item.quantity}`,
    };
  }

  return {
    title: item.description ?? "Line item",
    detail: `${item.quantity} ${item.unit ?? "item"}${
      item.unit_price !== null ? ` @ ${formatMoney(item.unit_price, "GBP")}` : ""
    }`,
  };
}

export default function QuoteDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useAuth();
  const [quote, setQuote] = useState<Quote | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [sending, setSending] = useState(false);
  // Sprint 039 (Workstream A) — emailing the quote for real, through
  // Sprint 038's DeliveryService. Kept separate from `sending` (which
  // drives the manual "mark as sent") so a page can never show both
  // actions busy at once.
  const [emailing, setEmailing] = useState(false);
  const [deliveryNotice, setDeliveryNotice] = useState<string | null>(null);
  // Bumped after a send so the timeline below re-reads rather than
  // showing a stale history that is missing the message just sent.
  const [historyKey, setHistoryKey] = useState(0);
  // Sprint 039 (Workstream C) — the compose-and-review panel. Closed by
  // default: writing a message is a deliberate act, not the first thing
  // someone opening a quote should be looking at.
  const [composing, setComposing] = useState(false);
  const [draftingAvailable, setDraftingAvailable] = useState(false);
  const [handingOff, setHandingOff] = useState(false);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    // Whether GeoCore AI can draft in this deployment. A failed read
    // simply hides the drafting controls — the composer still lets a
    // person write and send a message themselves, which is the part that
    // must always work.
    api
      .getAICapabilities()
      .then((capabilities) => setDraftingAvailable(capabilities.drafting))
      .catch(() => {});
    api
      .getQuote(params.id)
      .then((loaded) => {
        setQuote(loaded);
        if (loaded.customer_id) {
          api.getCustomer(loaded.customer_id).then(setCustomer).catch(() => {});
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

  async function run(
    action: () => Promise<void>,
    setBusy: (busy: boolean) => void,
    failure: string
  ) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : failure);
    } finally {
      setBusy(false);
    }
  }

  const canAct = role === "Owner" || role === "Staff";
  const currency = quote?.currency ?? "GBP";

  const money = (value: number | null | undefined) =>
    value === null || value === undefined ? "—" : formatMoney(value, currency);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <Link href="/quotes" className="tap-link text-sm text-muted hover:text-foreground">
          &larr; Quotes
        </Link>
      </div>

      {error && (
        <Card className="mb-6">
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {deliveryNotice && (
        <Card className="mb-6 border-info/25 bg-info/5">
          <CardContent className="py-4">
            <p className="text-sm text-foreground">{deliveryNotice}</p>
          </CardContent>
        </Card>
      )}

      {!error && !quote && <p className="text-sm text-muted">Loading…</p>}

      {quote && (
        <>
          <Card>
            <CardContent>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONE[quote.status] ?? "neutral"}>
                      {QUOTE_STATUS_LABELS[quote.status] ?? quote.status}
                    </Badge>
                    {quote.quote_kind === "stone" && (
                      <Badge tone="champagne">Stone &amp; worktops</Badge>
                    )}
                  </div>
                  <h1 className="mt-2 text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
                    {quote.title ??
                      (quote.material
                        ? `${quote.material}${quote.thickness ? ` (${quote.thickness})` : ""}`
                        : "Quote")}
                  </h1>
                  <p className="text-xs text-muted">
                    Created {formatRelativeTime(quote.created_at)}
                    {quote.valid_until && ` · valid until ${formatDate(quote.valid_until)}`}
                  </p>
                </div>
                <span className="text-2xl font-semibold text-foreground">
                  {money(quote.total)}
                </span>
              </div>

              <dl className="mt-6 grid grid-cols-1 gap-4 border-t border-border pt-4 sm:grid-cols-2">
                <div className="min-w-0">
                  <dt className="text-xs font-medium text-muted">Customer</dt>
                  <dd className="truncate text-sm text-foreground">
                    {customer ? (
                      <Link
                        href={`/customers/${customer.id}`}
                        className="text-accent hover:underline"
                      >
                        {customer.company_name || customer.name}
                      </Link>
                    ) : (
                      "No customer linked"
                    )}
                  </dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-xs font-medium text-muted">Site</dt>
                  <dd className="text-sm text-foreground">
                    {[
                      quote.site_address_line1,
                      quote.site_city,
                      quote.site_postcode ?? quote.postcode,
                    ]
                      .filter(Boolean)
                      .join(", ") || "—"}
                  </dd>
                </div>
              </dl>

              {quote.scope_of_works && (
                <div className="mt-4 border-t border-border pt-4">
                  <p className="text-xs font-medium text-muted">Scope of works</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">
                    {quote.scope_of_works}
                  </p>
                </div>
              )}

              <div className="mt-6 flex flex-wrap gap-2 border-t border-border pt-4">
                {quote.status === "draft" && canAct && (
                  <>
                    {/* Sprint 039 — the primary action is now the one that
                        actually delivers. "Mark as sent" stays beside it,
                        because a business that posts the PDF or hands it
                        over on site still needs to record that it went. */}
                    <Button
                      disabled={emailing || sending}
                      onClick={() =>
                        run(
                          async () => {
                            const result = await api.sendQuoteByEmail(quote.id);
                            setQuote(result.quote);
                            setHistoryKey((key) => key + 1);
                            // The communication row is authoritative about
                            // what happened — never a cheerful "Sent!"
                            // regardless of outcome.
                            setDeliveryNotice(
                              result.communication.status === "sent"
                                ? "Emailed to the customer. You'll see it confirmed as delivered here once their mail server accepts it."
                                : `Not delivered — ${STATUS_LABEL[result.communication.status].toLowerCase()}. ${
                                    result.communication.failure_detail ?? ""
                                  }`.trim()
                            );
                          },
                          setEmailing,
                          "Could not email the quote."
                        )
                      }
                    >
                      <MailIcon className="h-4 w-4" />
                      {emailing ? "Sending…" : "Email to customer"}
                    </Button>

                    <Button
                      variant="outline"
                      disabled={sending || emailing}
                      onClick={() =>
                        run(
                          async () => setQuote(await api.sendQuote(quote.id)),
                          setSending,
                          "Could not mark the quote as sent."
                        )
                      }
                    >
                      <SendIcon className="h-4 w-4" />
                      {sending ? "Saving…" : "Mark as sent"}
                    </Button>
                  </>
                )}

                {(quote.status === "draft" || quote.status === "sent") && canAct && (
                  <Button
                    variant={quote.status === "sent" ? "primary" : "outline"}
                    disabled={approving}
                    onClick={() =>
                      run(
                        async () => setQuote(await api.approveQuote(quote.id)),
                        setApproving,
                        "Could not approve the quote."
                      )
                    }
                  >
                    {approving ? "Approving…" : "Approve"}
                  </Button>
                )}

                {quote.status === "approved" && canAct && (
                  <Button
                    disabled={handingOff}
                    onClick={() =>
                      run(
                        async () => {
                          const project = await api.handoffQuote(quote.id);
                          router.push(`/projects/${project.id}`);
                        },
                        setHandingOff,
                        "Could not hand off the quote."
                      )
                    }
                  >
                    {handingOff ? "Creating…" : "Create the project"}
                  </Button>
                )}

                <Button
                  variant="outline"
                  disabled={downloading}
                  onClick={() =>
                    run(
                      () => api.downloadInvoice(quote.id),
                      setDownloading,
                      "Could not download the PDF."
                    )
                  }
                >
                  {downloading ? "Preparing…" : "Download PDF"}
                </Button>
              </div>

              {quote.status === "draft" && canAct && (
                // Stated plainly rather than implied. GeoCore has no
                // email, SMS or messaging channel — "Mark as sent" records
                // that a person sent it, and pretending otherwise here
                // would be the exact kind of claim this sprint forbids.
                <p className="mt-3 text-xs text-muted">
                  GeoCore doesn&rsquo;t email customers yet. Download the PDF or share a
                  portal link, then mark the quote as sent so it can be chased.
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="mt-6">
            <CardHeader>
              <CardTitle>
                {quote.items.length} line{quote.items.length === 1 ? "" : "s"}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              <ul className="flex flex-col gap-2">
                {quote.items.map((item) => {
                  const { title, detail } = describeLine(item);
                  return (
                    <li
                      key={item.id}
                      className="flex items-start justify-between gap-3 rounded-lg bg-surface-hover px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{title}</p>
                        <p className="text-xs text-muted">{detail}</p>
                      </div>
                      <span className="shrink-0 text-sm text-foreground">
                        {money(item.line_total)}
                      </span>
                    </li>
                  );
                })}
              </ul>

              <dl className="mt-5 space-y-2 border-t border-border pt-4 text-sm">
                <div className="flex justify-between">
                  <dt className="text-muted">Subtotal</dt>
                  <dd className="text-foreground">
                    {money(quote.subtotal ?? quote.price_before_vat)}
                  </dd>
                </div>
                {quote.discount_amount ? (
                  <div className="flex justify-between">
                    <dt className="text-muted">Discount</dt>
                    <dd className="text-foreground">−{money(quote.discount_amount)}</dd>
                  </div>
                ) : null}
                <div className="flex justify-between">
                  <dt className="text-muted">
                    VAT ({Math.round((quote.vat_rate ?? 0.2) * 100)}%)
                  </dt>
                  <dd className="text-foreground">{money(quote.vat)}</dd>
                </div>
                <div className="flex justify-between border-t border-border pt-2 text-base">
                  <dt className="font-semibold text-foreground">Total</dt>
                  <dd className="font-semibold text-foreground">{money(quote.total)}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {(quote.exclusions || quote.terms) && (
            <Card className="mt-6">
              <CardHeader>
                <CardTitle>Terms &amp; exclusions</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4 pt-4">
                {quote.exclusions && (
                  <div>
                    <p className="text-xs font-medium text-muted">Exclusions</p>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">
                      {quote.exclusions}
                    </p>
                  </div>
                )}
                {quote.terms && (
                  <div>
                    <p className="text-xs font-medium text-muted">Payment terms</p>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">
                      {quote.terms}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Sprint 039 (Workstream C) — write, review and send a message
              about this quote. Opening it is a click, because the review
              step only means something if a person chose to be here. */}
          {quote.customer_id && canAct && (
            <div className="mt-6">
              {composing ? (
                <MessageComposer
                  customerId={quote.customer_id}
                  customerName={customer?.name}
                  quoteId={quote.id}
                  defaultKind={quote.status === "sent" ? "quote_follow_up" : "quote_delivery"}
                  draftingAvailable={draftingAvailable}
                  onSent={() => setHistoryKey((key) => key + 1)}
                  onClose={() => setComposing(false)}
                />
              ) : (
                <Button variant="outline" onClick={() => setComposing(true)}>
                  <MailIcon className="h-4 w-4" />
                  Message the customer
                </Button>
              )}
            </div>
          )}

          {/* Sprint 039 (Workstream A) — what has been sent about this
              quote, and whether it arrived. `key` forces a re-read after a
              send rather than leaving a history that is missing it. */}
          <div className="mt-6">
            <CommunicationTimeline
              key={historyKey}
              title="Communications"
              filters={{ quoteId: quote.id }}
              emptyTitle="Nothing sent about this quote yet"
              emptyDescription="Email this quote to your customer and it will be recorded here, with whether it arrived."
            />
          </div>
        </>
      )}
    </div>
  );
}
