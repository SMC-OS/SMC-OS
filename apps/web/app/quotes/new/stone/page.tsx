"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP } from "@/lib/utils";
import {
  ITEM_TYPE_LABELS,
  ITEM_TYPES,
  MATERIAL_OPTIONS,
  THICKNESS_OPTIONS,
  type AIQuoteItemDraft,
  type ItemType,
  type QuoteResult,
} from "@/types/quote";
import type { Customer } from "@/types/customer";

interface ItemRow {
  key: string;
  item_type: ItemType;
  material: string;
  thickness: string;
  quantity: string;
  length_mm: string;
  width_mm: string;
}

let nextRowKey = 0;
function newRowKey() {
  nextRowKey += 1;
  return `row-${nextRowKey}`;
}

function blankItem(overrides: Partial<ItemRow> = {}): ItemRow {
  return {
    key: newRowKey(),
    item_type: "worktop",
    material: MATERIAL_OPTIONS[0],
    thickness: THICKNESS_OPTIONS[0],
    quantity: "1",
    length_mm: "",
    width_mm: "650",
    ...overrides,
  };
}

function draftToRow(draft: AIQuoteItemDraft): ItemRow {
  return blankItem({
    item_type: draft.item_type,
    material: draft.material ?? MATERIAL_OPTIONS[0],
    thickness: draft.thickness ?? THICKNESS_OPTIONS[0],
    quantity: draft.quantity !== null ? String(draft.quantity) : "1",
    length_mm: draft.length_mm !== null ? String(draft.length_mm) : "",
    width_mm: draft.width_mm !== null ? String(draft.width_mm) : "650",
  });
}

export default function NewQuotePage() {
  const { isAuthenticated } = useAuth();
  const [customer, setCustomer] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [postcode, setPostcode] = useState("");
  const [items, setItems] = useState<ItemRow[]>([blankItem()]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QuoteResult | null>(null);
  const [downloading, setDownloading] = useState(false);

  // AI Quotation Generator — separate state from the manual form's
  // submitting/error, so an AI failure is never confused with a
  // calculation failure, and the manual form stays usable regardless.
  const [aiText, setAiText] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiDraftItems, setAiDraftItems] = useState<AIQuoteItemDraft[] | null>(null);
  const [aiWarnings, setAiWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.getCustomers().then(setCustomers).catch(() => {});
  }, [isAuthenticated]);

  function handleCustomerSelect(id: string) {
    const selected = customers.find((c) => c.id === id);
    setCustomerId(id);
    if (selected) setCustomer(selected.name);
  }

  function updateItem(key: string, patch: Partial<ItemRow>) {
    setItems((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function addItem() {
    setItems((rows) => [...rows, blankItem()]);
  }

  function removeItem(key: string) {
    setItems((rows) => (rows.length > 1 ? rows.filter((r) => r.key !== key) : rows));
  }

  function duplicateItem(key: string) {
    setItems((rows) => {
      const index = rows.findIndex((r) => r.key === key);
      if (index === -1) return rows;
      const copy = { ...rows[index], key: newRowKey() };
      return [...rows.slice(0, index + 1), copy, ...rows.slice(index + 1)];
    });
  }

  function moveItem(key: string, direction: -1 | 1) {
    setItems((rows) => {
      const index = rows.findIndex((r) => r.key === key);
      const target = index + direction;
      if (index === -1 || target < 0 || target >= rows.length) return rows;
      const next = [...rows];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const quote = await api.createQuote({
        customer: customer || "Unknown",
        customer_id: customerId || null,
        postcode: postcode || undefined,
        items: items.map((row) => ({
          item_type: row.item_type,
          material: row.material,
          thickness: row.thickness,
          quantity: Number(row.quantity) || 1,
          length_mm: Number(row.length_mm) || 0,
          width_mm: Number(row.width_mm) || 650,
          unit_input: "mm",
        })),
      });
      setResult(quote);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGenerateDraft() {
    setAiLoading(true);
    setAiError(null);
    setAiDraftItems(null);
    setAiWarnings([]);

    try {
      const draft = await api.generateQuoteDraft(aiText);
      setCustomer((c) => draft.customer ?? c);
      setPostcode((p) => draft.postcode ?? p);
      setAiDraftItems(draft.items);
      setAiWarnings(draft.warnings);
    } catch (err) {
      setAiError(
        err instanceof ApiError
          ? err.status === 503
            ? "AI quotation drafting is not configured yet."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setAiLoading(false);
    }
  }

  function applyAiDraft() {
    if (!aiDraftItems || aiDraftItems.length === 0) return;
    // Never auto-submitted, never priced here — this only pre-fills the
    // item rows below for the user to review before calculating.
    setItems(aiDraftItems.map(draftToRow));
    setAiDraftItems(null);
  }

  async function handleDownload() {
    if (!result) return;
    setDownloading(true);
    try {
      await api.downloadInvoice(result.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download the invoice.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      {/* Sprint 036 (Workstream E) — this is now the specialist stone
          and worktop template, not "the" quote form. It is unchanged in
          behaviour: the same slab calculator, the same material
          catalogue, the same AI extraction. What changed is that it no
          longer stands for every kind of work GeoCore quotes. */}
      <div className="mb-6">
        <Link href="/quotes/new" className="text-sm text-muted hover:text-foreground">
          &larr; New quote
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          Stone &amp; worktop quote
        </h1>
        <p className="mt-1 text-sm text-muted">
          Priced from your material catalogue by slab area. Add a worktop, an
          island, splashbacks or upstands — each with its own material and
          dimensions in mm.
        </p>
        <p className="mt-2 text-sm text-muted">
          Quoting other work?{" "}
          <Link href="/quotes/new" className="font-medium text-accent hover:underline">
            Use the general construction quote
          </Link>
          .
        </p>
      </div>

      {isAuthenticated && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Draft with AI</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <p className="mb-3 text-sm text-muted">
              Describe the job in plain text — this only pre-fills the items below for
              you to review. It never submits or prices anything.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <textarea
                className="h-20 flex-1 rounded-lg border border-border bg-background p-3 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent"
                value={aiText}
                onChange={(e) => setAiText(e.target.value)}
                placeholder="e.g. Calacatta Oro 20mm for a 2400 x 600 worktop, a 2200 x 1000 island and two 1200 x 600 splashbacks"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleGenerateDraft}
                disabled={aiLoading || !aiText.trim()}
              >
                {aiLoading ? "Generating…" : "Generate Draft"}
              </Button>
            </div>

            {aiError && (
              <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                {aiError}
              </p>
            )}

            {aiWarnings.length > 0 && (
              <div className="mt-3 flex flex-col gap-1.5">
                {aiWarnings.map((w) => (
                  <Badge key={w} tone="warning" className="w-fit">
                    {w}
                  </Badge>
                ))}
              </div>
            )}

            {aiDraftItems && aiDraftItems.length > 0 && (
              <div className="mt-4 rounded-lg border border-border bg-background p-3">
                <p className="mb-2 text-sm font-medium text-foreground">
                  Interpreted {aiDraftItems.length} item{aiDraftItems.length > 1 ? "s" : ""} —
                  check these before adding to the quote:
                </p>
                <ul className="flex flex-col gap-2">
                  {aiDraftItems.map((item, i) => (
                    <li key={i} className="rounded-md bg-surface-hover px-3 py-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-foreground">
                          {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
                        </span>
                        {item.material_match_status === "found" && (
                          <Badge tone="success">{item.material}</Badge>
                        )}
                        {item.material_match_status === "multiple" && (
                          <Badge tone="warning">Ambiguous — pick manually</Badge>
                        )}
                        {item.material_match_status === "not_found" && (
                          <Badge tone="danger">Not found: {item.material_raw}</Badge>
                        )}
                        {item.material_match_status === null && (
                          <Badge tone="neutral">No material stated</Badge>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        {item.quantity ?? 1} x{" "}
                        {item.length_mm !== null ? `${item.length_mm}mm` : "? length"} x{" "}
                        {item.width_mm !== null ? `${item.width_mm}mm` : "? width"}
                        {item.thickness ? ` x ${item.thickness}` : ""}
                        {item.unit_input && item.unit_input !== "mm"
                          ? ` (entered as ${item.unit_input})`
                          : ""}
                      </p>
                      {item.material_match_status === "multiple" && (
                        <p className="mt-1 text-xs text-muted">
                          Candidates: {item.material_candidates.join(", ")}
                        </p>
                      )}
                      {item.warnings.length > 0 && (
                        <p className="mt-1 text-xs text-warning">{item.warnings.join(" ")}</p>
                      )}
                    </li>
                  ))}
                </ul>
                <Button type="button" size="sm" className="mt-3" onClick={applyAiDraft}>
                  Use these items
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <form onSubmit={handleSubmit}>
        <Card className="mb-6">
          <CardContent>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Customer name" htmlFor="customer" className="sm:col-span-2">
                <Input
                  id="customer"
                  required
                  value={customer}
                  onChange={(e) => setCustomer(e.target.value)}
                  placeholder="e.g. Sarah Whitfield"
                />
              </Field>

              {isAuthenticated && customers.length > 0 && (
                <Field
                  label="Link to existing customer (optional)"
                  htmlFor="customerId"
                  className="sm:col-span-2"
                >
                  <Select
                    id="customerId"
                    value={customerId}
                    onChange={(e) => handleCustomerSelect(e.target.value)}
                  >
                    <option value="">— Not linked —</option>
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}

              <Field label="Postcode (optional)" htmlFor="postcode">
                <Input
                  id="postcode"
                  value={postcode}
                  onChange={(e) => setPostcode(e.target.value)}
                  placeholder="SW1A 1AA"
                />
              </Field>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          {items.map((row, index) => (
            <Card key={row.key}>
              <CardContent className="pt-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted">
                    Item {index + 1}
                  </span>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={index === 0}
                      onClick={() => moveItem(row.key, -1)}
                      aria-label="Move item up"
                    >
                      ↑
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={index === items.length - 1}
                      onClick={() => moveItem(row.key, 1)}
                      aria-label="Move item down"
                    >
                      ↓
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => duplicateItem(row.key)}
                    >
                      Duplicate
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={items.length === 1}
                      onClick={() => removeItem(row.key)}
                    >
                      Remove
                    </Button>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <Field label="Type" htmlFor={`${row.key}-type`}>
                    <Select
                      id={`${row.key}-type`}
                      value={row.item_type}
                      onChange={(e) =>
                        updateItem(row.key, { item_type: e.target.value as ItemType })
                      }
                    >
                      {ITEM_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {ITEM_TYPE_LABELS[t]}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field label="Material" htmlFor={`${row.key}-material`}>
                    <Select
                      id={`${row.key}-material`}
                      value={row.material}
                      onChange={(e) => updateItem(row.key, { material: e.target.value })}
                    >
                      {MATERIAL_OPTIONS.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field label="Thickness" htmlFor={`${row.key}-thickness`}>
                    <Select
                      id={`${row.key}-thickness`}
                      value={row.thickness}
                      onChange={(e) => updateItem(row.key, { thickness: e.target.value })}
                    >
                      {THICKNESS_OPTIONS.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </Select>
                  </Field>

                  <Field label="Quantity" htmlFor={`${row.key}-qty`}>
                    <Input
                      id={`${row.key}-qty`}
                      type="number"
                      min="1"
                      step="1"
                      value={row.quantity}
                      onChange={(e) => updateItem(row.key, { quantity: e.target.value })}
                    />
                  </Field>

                  <Field label="Length (mm)" htmlFor={`${row.key}-length`}>
                    <Input
                      id={`${row.key}-length`}
                      type="number"
                      step="1"
                      min="0"
                      required
                      value={row.length_mm}
                      onChange={(e) => updateItem(row.key, { length_mm: e.target.value })}
                      placeholder="e.g. 2400"
                    />
                  </Field>

                  <Field label="Width/Depth (mm)" htmlFor={`${row.key}-width`}>
                    <Input
                      id={`${row.key}-width`}
                      type="number"
                      step="1"
                      min="0"
                      value={row.width_mm}
                      onChange={(e) => updateItem(row.key, { width_mm: e.target.value })}
                      placeholder="e.g. 600"
                    />
                  </Field>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="mt-4 flex items-center justify-between">
          <Button type="button" variant="outline" onClick={addItem}>
            + Add item
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Calculating…" : "Calculate Quote"}
          </Button>
        </div>

        {error && (
          <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>
        )}
      </form>

      {result && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Quote for {result.customer}</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <ul className="mb-4 flex flex-col gap-2">
              {result.items.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center justify-between rounded-lg bg-surface-hover px-3 py-2 text-sm"
                >
                  <div>
                    <p className="font-medium text-foreground">
                      {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type} — {item.material} (
                      {item.thickness})
                    </p>
                    <p className="text-xs text-muted">
                      {item.quantity} x {item.length_mm}mm x {item.width_mm}mm ·{" "}
                      {item.slabs} slab{item.slabs === 1 ? "" : "s"}
                    </p>
                  </div>
                  <span className="text-foreground">
                    {item.line_total !== null ? formatCurrencyGBP(item.line_total) : "—"}
                  </span>
                </li>
              ))}
            </ul>

            <dl className="grid grid-cols-2 gap-y-2 border-t border-border pt-4 text-sm">
              <dt className="text-muted">Subtotal</dt>
              <dd className="text-right text-foreground">
                {formatCurrencyGBP(result.price_before_vat)}
              </dd>
              <dt className="text-muted">VAT (20%)</dt>
              <dd className="text-right text-foreground">{formatCurrencyGBP(result.vat)}</dd>
              <dt className="font-semibold text-foreground">Total</dt>
              <dd className="text-right text-lg font-semibold text-foreground">
                {formatCurrencyGBP(result.total)}
              </dd>
            </dl>

            <div className="mt-4 border-t border-border pt-4">
              {isAuthenticated ? (
                <Button onClick={handleDownload} disabled={downloading} variant="outline">
                  {downloading ? "Downloading…" : "Download Invoice"}
                </Button>
              ) : (
                <p className="text-sm text-muted">
                  <Link href="/login" className="text-accent hover:underline">
                    Sign in
                  </Link>{" "}
                  to download the invoice.
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
