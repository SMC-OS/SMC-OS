"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { currencySymbol, daysFromTodayISO, formatMoney } from "@/lib/utils";
import type {
  GeneralQuoteLineRequest,
  GeneralQuoteRequest,
  LineKind,
  Quote,
  QuoteUnit,
  Trade,
} from "@/types/quote";
import { LINE_KINDS, LINE_KIND_LABELS } from "@/types/quote";
import type { Customer } from "@/types/customer";

interface LineRow extends GeneralQuoteLineRequest {
  key: string;
}

let nextKey = 0;
function blankLine(overrides: Partial<LineRow> = {}): LineRow {
  nextKey += 1;
  return {
    key: `line-${nextKey}`,
    line_kind: "labour",
    description: "",
    quantity: 1,
    unit: "item",
    unit_price: 0,
    ...overrides,
  };
}

// Sprint 039 Production Readiness Defect Gate, Blocker 5 — a quote being
// edited is always a general quote in draft (the backend refuses
// anything else), so every item is a plain labour/material/other line;
// none of the stone-only columns are ever populated here.
function linesFromQuote(quote: Quote): LineRow[] {
  return quote.items.map((item) =>
    blankLine({
      line_kind: item.line_kind === "stone" ? "other" : item.line_kind,
      description: item.description ?? "",
      quantity: item.quantity,
      unit: item.unit ?? "item",
      unit_price: item.unit_price ?? 0,
      notes: item.notes,
    })
  );
}

/**
 * The general construction quote builder — Sprint 036, Workstream E.
 *
 * This is GeoCore's default quote now. It can price a bathroom refit, a
 * roof, an extension, a rewire or a set of worktops, because a line item
 * is described in words and priced as quantity x rate rather than being
 * a slab.
 *
 * Totals are computed here as the user types, using exactly the rounding
 * rule the backend uses — each line rounded to 2dp, then summed — so the
 * figure on screen is the figure that gets saved. Computing it any other
 * way produces a quote whose lines do not add up to its total, which is
 * the one arithmetic error a quote must never make. The server re-prices
 * from the same lines on submit and its answer is authoritative; this is
 * a preview, not a second source of truth.
 */
export function GeneralQuoteBuilder({
  initialCustomerId,
  existingQuote,
}: {
  initialCustomerId?: string;
  /** Sprint 039 Production Readiness Defect Gate, Blocker 5 — when set,
   * the builder opens pre-filled from this quote and PATCHes it on
   * submit instead of creating a new one. Only ever passed a draft
   * general quote; the /quotes/[id]/edit page enforces that before this
   * component is ever rendered. */
  existingQuote?: Quote;
}) {
  const { currency } = useWorkspace();
  const symbol = currencySymbol(currency);

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [units, setUnits] = useState<QuoteUnit[]>([]);

  const [customerId, setCustomerId] = useState(
    existingQuote?.customer_id ?? initialCustomerId ?? ""
  );
  const [title, setTitle] = useState(existingQuote?.title ?? "");
  const [trade, setTrade] = useState(existingQuote?.trade ?? "");
  const [addressLine1, setAddressLine1] = useState(
    existingQuote?.site_address_line1 ?? ""
  );
  const [addressLine2, setAddressLine2] = useState(
    existingQuote?.site_address_line2 ?? ""
  );
  const [city, setCity] = useState(existingQuote?.site_city ?? "");
  const [postcode, setPostcode] = useState(existingQuote?.site_postcode ?? "");
  const [scope, setScope] = useState(existingQuote?.scope_of_works ?? "");
  const [exclusions, setExclusions] = useState(existingQuote?.exclusions ?? "");
  const [terms, setTerms] = useState(existingQuote?.terms ?? "");
  const [notes, setNotes] = useState(existingQuote?.notes ?? "");
  const [validUntil, setValidUntil] = useState(
    existingQuote?.valid_until ?? daysFromTodayISO(30)
  );
  const [vatRate, setVatRate] = useState(
    existingQuote ? String(Math.round(existingQuote.vat_rate * 100)) : "20"
  );
  const [discount, setDiscount] = useState(
    existingQuote?.discount_amount ? String(existingQuote.discount_amount) : ""
  );
  const [lines, setLines] = useState<LineRow[]>(() =>
    existingQuote ? linesFromQuote(existingQuote) : [blankLine()]
  );

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Quote | null>(null);

  useEffect(() => {
    api.getCustomers(200).then(setCustomers).catch(() => {});
    api.getTrades().then(setTrades).catch(() => {});
    api.getQuoteUnits().then(setUnits).catch(() => {});
  }, []);

  // When a customer is chosen and no site address has been typed yet,
  // prefill it from their own address. Their address is where the work
  // usually is, and someone who needs a different site address can just
  // type over it.
  function selectCustomer(id: string) {
    setCustomerId(id);
    const selected = customers.find((customer) => customer.id === id);
    if (!selected) return;
    if (!addressLine1 && !city && !postcode) {
      setAddressLine1(selected.address_line1 ?? "");
      setAddressLine2(selected.address_line2 ?? "");
      setCity(selected.city ?? "");
      setPostcode(selected.postcode ?? "");
    }
  }

  function updateLine(key: string, patch: Partial<LineRow>) {
    setLines((rows) => rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  const totals = useMemo(() => {
    const lineTotals = lines.map((line) =>
      Math.round(line.quantity * line.unit_price * 100) / 100
    );
    const subtotal = Math.round(lineTotals.reduce((sum, value) => sum + value, 0) * 100) / 100;
    const rate = (Number(vatRate) || 0) / 100;
    const discountAmount = Math.min(
      Math.round((Number(discount) || 0) * 100) / 100,
      subtotal
    );
    const beforeVat = Math.round((subtotal - discountAmount) * 100) / 100;
    const vat = Math.round(beforeVat * rate * 100) / 100;
    return {
      lineTotals,
      subtotal,
      discountAmount,
      beforeVat,
      vat,
      total: Math.round((beforeVat + vat) * 100) / 100,
    };
  }, [lines, vatRate, discount]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const payload: GeneralQuoteRequest = {
      customer_id: customerId || null,
      title: title.trim(),
      trade: trade || null,
      site_address_line1: addressLine1.trim() || null,
      site_address_line2: addressLine2.trim() || null,
      site_city: city.trim() || null,
      site_postcode: postcode.trim() || null,
      scope_of_works: scope.trim() || null,
      exclusions: exclusions.trim() || null,
      terms: terms.trim() || null,
      notes: notes.trim() || null,
      valid_until: validUntil || null,
      vat_rate: (Number(vatRate) || 0) / 100,
      discount_amount: discount ? Number(discount) : null,
      // `key` is a render identity for React, not part of the request —
      // stripped explicitly rather than destructured away, so no unused
      // binding is left behind.
      lines: lines.map((line) => ({
        line_kind: line.line_kind,
        description: line.description.trim(),
        quantity: line.quantity,
        unit: line.unit,
        unit_price: line.unit_price,
        notes: line.notes ?? null,
      })),
    };

    try {
      setCreated(
        existingQuote
          ? await api.updateGeneralQuote(existingQuote.id, payload)
          : await api.createGeneralQuote(payload)
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 422
            ? "Check the quote — every line needs a description, and quantities and rates cannot be negative."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <Card>
        <CardContent className="text-center">
          <Badge tone="success">{existingQuote ? "Quote updated" : "Quote created"}</Badge>
          <p className="mt-3 text-2xl font-semibold text-foreground">
            {formatMoney(created.total ?? 0, created.currency)}
          </p>
          <p className="mt-1 text-sm text-muted">
            {created.title} · including {formatMoney(created.vat ?? 0, created.currency)} VAT
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Link href={`/quotes/${created.id}`}>
              <Button>{existingQuote ? "Back to the quote" : "Open the quote"}</Button>
            </Link>
            <Link href="/quotes">
              <Button variant="outline">All quotes</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>The job</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5 pt-4">
          <Field
            label="Quote title"
            htmlFor="title"
            required
            hint="What the customer will see at the top of the document."
          >
            <Input
              id="title"
              required
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Bathroom refit, 14 Elm Road"
            />
          </Field>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field label="Customer" htmlFor="customer">
              <Select
                id="customer"
                value={customerId}
                onChange={(e) => selectCustomer(e.target.value)}
              >
                <option value="">— No customer linked —</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.company_name || customer.name}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Type of work" htmlFor="trade">
              <Select id="trade" value={trade} onChange={(e) => setTrade(e.target.value)}>
                <option value="">— Not specified —</option>
                {trades.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="border-t border-border pt-5">
            <p className="mb-3 text-sm font-medium text-foreground">Site address</p>
            <div className="flex flex-col gap-5">
              <Field label="Address line 1" htmlFor="siteAddress1">
                <Input
                  id="siteAddress1"
                  value={addressLine1}
                  onChange={(e) => setAddressLine1(e.target.value)}
                  placeholder="14 Elm Road"
                />
              </Field>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field label="Town or city" htmlFor="siteCity">
                  <Input id="siteCity" value={city} onChange={(e) => setCity(e.target.value)} />
                </Field>
                <Field label="Postcode" htmlFor="sitePostcode">
                  <Input
                    id="sitePostcode"
                    value={postcode}
                    onChange={(e) => setPostcode(e.target.value)}
                    className="uppercase"
                  />
                </Field>
              </div>
            </div>
          </div>

          <Field
            label="Scope of works"
            htmlFor="scope"
            hint="What you are actually going to do. This appears on the quote."
          >
            <Textarea
              id="scope"
              rows={4}
              value={scope}
              onChange={(e) => setScope(e.target.value)}
              placeholder="Strip out existing bathroom, first and second fix plumbing, tile floor and walls, fit new suite and shower enclosure, make good and remove all waste."
            />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Line items</CardTitle>
          <Button variant="outline" size="sm" onClick={() => setLines((rows) => [...rows, blankLine()])}>
            <PlusIcon className="h-4 w-4" />
            Add line
          </Button>
        </CardHeader>

        <CardContent className="pt-4">
          <div className="flex flex-col gap-4">
            {lines.map((line, index) => (
              <div
                key={line.key}
                className="rounded-xl border border-border bg-surface-raised p-4"
              >
                <div className="mb-3 flex items-center justify-between gap-3">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted">
                    Line {index + 1}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-foreground">
                      {formatMoney(totals.lineTotals[index] ?? 0, currency)}
                    </span>
                    {lines.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove line ${index + 1}`}
                        onClick={() =>
                          setLines((rows) => rows.filter((row) => row.key !== line.key))
                        }
                      >
                        <TrashIcon className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-4">
                  <Field label="Description" htmlFor={`desc-${line.key}`} required>
                    <Input
                      id={`desc-${line.key}`}
                      required
                      value={line.description}
                      onChange={(e) => updateLine(line.key, { description: e.target.value })}
                      placeholder="e.g. Strip out existing bathroom"
                    />
                  </Field>

                  {/* Four controls in a row on desktop, stacked into two
                      rows of two on a phone — four number inputs side by
                      side at 360px is unusable. */}
                  <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                    <Field label="Type" htmlFor={`kind-${line.key}`}>
                      <Select
                        id={`kind-${line.key}`}
                        value={line.line_kind}
                        onChange={(e) =>
                          updateLine(line.key, { line_kind: e.target.value as LineKind })
                        }
                      >
                        {LINE_KINDS.map((kind) => (
                          <option key={kind} value={kind}>
                            {LINE_KIND_LABELS[kind]}
                          </option>
                        ))}
                      </Select>
                    </Field>

                    <Field label="Quantity" htmlFor={`qty-${line.key}`}>
                      <Input
                        id={`qty-${line.key}`}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        value={line.quantity}
                        onChange={(e) =>
                          updateLine(line.key, { quantity: Number(e.target.value) || 0 })
                        }
                      />
                    </Field>

                    <Field label="Unit" htmlFor={`unit-${line.key}`}>
                      <Select
                        id={`unit-${line.key}`}
                        value={line.unit}
                        onChange={(e) => updateLine(line.key, { unit: e.target.value })}
                      >
                        {units.map((unit) => (
                          <option key={unit.key} value={unit.key}>
                            {unit.label}
                          </option>
                        ))}
                      </Select>
                    </Field>

                    <Field label={`Rate (${symbol})`} htmlFor={`rate-${line.key}`}>
                      <Input
                        id={`rate-${line.key}`}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        value={line.unit_price}
                        onChange={(e) =>
                          updateLine(line.key, { unit_price: Number(e.target.value) || 0 })
                        }
                      />
                    </Field>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Price</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
            <Field label={`Discount (${symbol})`} htmlFor="discount">
              <Input
                id="discount"
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                placeholder="0.00"
              />
            </Field>
            <Field label="VAT rate (%)" htmlFor="vatRate">
              <Input
                id="vatRate"
                type="number"
                inputMode="decimal"
                min={0}
                max={100}
                step="0.5"
                value={vatRate}
                onChange={(e) => setVatRate(e.target.value)}
              />
            </Field>
            <Field
              label="Valid until"
              htmlFor="validUntil"
              hint="Used to chase unanswered quotes."
            >
              <Input
                id="validUntil"
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
              />
            </Field>
          </div>

          <dl className="mt-6 space-y-2 border-t border-border pt-4 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">Subtotal</dt>
              <dd className="font-medium text-foreground">
                {formatMoney(totals.subtotal, currency)}
              </dd>
            </div>
            {totals.discountAmount > 0 && (
              <div className="flex justify-between">
                <dt className="text-muted">Discount</dt>
                <dd className="font-medium text-foreground">
                  −{formatMoney(totals.discountAmount, currency)}
                </dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt className="text-muted">VAT ({vatRate || 0}%)</dt>
              <dd className="font-medium text-foreground">
                {formatMoney(totals.vat, currency)}
              </dd>
            </div>
            <div className="flex justify-between border-t border-border pt-2 text-base">
              <dt className="font-semibold text-foreground">Total</dt>
              <dd className="font-semibold text-foreground">
                {formatMoney(totals.total, currency)}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Terms &amp; exclusions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5 pt-4">
          <Field
            label="Exclusions"
            htmlFor="exclusions"
            hint="What this price does not cover. The single most useful thing on a construction quote."
          >
            <Textarea
              id="exclusions"
              rows={3}
              value={exclusions}
              onChange={(e) => setExclusions(e.target.value)}
              placeholder="Making good to decoration. Any structural work not identified at survey."
            />
          </Field>
          <Field label="Payment terms" htmlFor="terms">
            <Textarea
              id="terms"
              rows={2}
              value={terms}
              onChange={(e) => setTerms(e.target.value)}
              placeholder="50% on commencement, balance on completion."
            />
          </Field>
          <Field label="Internal notes" htmlFor="notes" hint="Not shown to the customer.">
            <Textarea
              id="notes"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>
        </CardContent>
      </Card>

      {error && (
        <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={submitting}>
          {submitting ? "Saving…" : existingQuote ? "Save changes" : "Create quote"}
        </Button>
        <span className="text-sm text-muted">
          Total {formatMoney(totals.total, currency)}
        </span>
      </div>
    </form>
  );
}
