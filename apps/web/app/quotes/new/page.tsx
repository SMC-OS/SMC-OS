"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Checkbox, Field, Input, Select } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP } from "@/lib/utils";
import { MATERIAL_OPTIONS, THICKNESS_OPTIONS, type QuoteResult } from "@/types/quote";
import type { Customer } from "@/types/customer";

const initialForm = {
  customer: "",
  customerId: "",
  material: MATERIAL_OPTIONS[0] as string,
  thickness: THICKNESS_OPTIONS[0] as string,
  kitchen_length: "",
  island: false,
  waterfall: "0",
  splashback: false,
  upstands: false,
  postcode: "",
};

export default function NewQuotePage() {
  const { isAuthenticated } = useAuth();
  const [form, setForm] = useState(initialForm);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QuoteResult | null>(null);
  const [downloading, setDownloading] = useState(false);

  // AI Quotation Generator v1 — separate state from the manual form's
  // submitting/error, so an AI failure is never confused with a
  // calculation failure, and the manual form stays usable regardless.
  const [aiText, setAiText] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiWarnings, setAiWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (!isAuthenticated) return;
    // Sign-in isn't required to calculate a quote (POST /quote is public,
    // matching the existing engine), but linking a customer needs the
    // customer list, which is auth-gated — only fetch it if signed in.
    api.getCustomers().then(setCustomers).catch(() => {});
  }, [isAuthenticated]);

  function handleCustomerSelect(customerId: string) {
    const selected = customers.find((c) => c.id === customerId);
    setForm((f) => ({
      ...f,
      customerId,
      customer: selected ? selected.name : f.customer,
    }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const quote = await api.createQuote({
        customer: form.customer || "Unknown",
        customer_id: form.customerId || null,
        material: form.material,
        thickness: form.thickness,
        kitchen_length: Number(form.kitchen_length) || 0,
        island: form.island,
        waterfall: Number(form.waterfall) || 0,
        splashback: form.splashback,
        upstands: form.upstands,
        postcode: form.postcode || undefined,
      });

      // Sprint 007: the backend now logs this itself (app/quotes/service.py)
      // — no separate frontend api.logActivity() call needed anymore.
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
    setAiWarnings([]);

    try {
      const draft = await api.generateQuoteDraft(aiText);

      // Pre-fills the existing manual form — never auto-submitted, never
      // priced here. The user reviews every field below before calculating.
      setForm((f) => ({
        ...f,
        customer: draft.customer ?? f.customer,
        material: draft.material ?? f.material,
        thickness: draft.thickness ?? f.thickness,
        kitchen_length:
          draft.kitchen_length !== null ? String(draft.kitchen_length) : f.kitchen_length,
        island: draft.island,
        waterfall: String(draft.waterfall),
        splashback: draft.splashback,
        upstands: draft.upstands,
        postcode: draft.postcode ?? f.postcode,
      }));
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
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <Link href="/quotes" className="text-sm text-muted hover:text-foreground">
          &larr; Quotes
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          New Quote
        </h1>
        <p className="mt-1 text-sm text-muted">
          Calculated live by the existing quote engine (POST /quote) — saved
          as a real quote record, invoice downloadable once calculated.
        </p>
      </div>

      {isAuthenticated && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>✨ Draft with AI</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <p className="mb-3 text-sm text-muted">
              Describe the job in plain text — this only pre-fills the form
              below for you to review. It never submits or prices anything.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <textarea
                className="h-20 flex-1 rounded-lg border border-border bg-background p-3 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent"
                value={aiText}
                onChange={(e) => setAiText(e.target.value)}
                placeholder="e.g. 3.5m kitchen in calacatta gold with an island, customer Sarah Whitfield"
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
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Customer name" htmlFor="customer" className="sm:col-span-2">
              <Input
                id="customer"
                required
                value={form.customer}
                onChange={(e) => setForm((f) => ({ ...f, customer: e.target.value }))}
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
                  value={form.customerId}
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

            <Field label="Material" htmlFor="material">
              <Select
                id="material"
                value={form.material}
                onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
              >
                {MATERIAL_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Thickness" htmlFor="thickness">
              <Select
                id="thickness"
                value={form.thickness}
                onChange={(e) => setForm((f) => ({ ...f, thickness: e.target.value }))}
              >
                {THICKNESS_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label="Kitchen run length (m)" htmlFor="kitchen_length">
              <Input
                id="kitchen_length"
                type="number"
                step="0.1"
                min="0"
                required
                value={form.kitchen_length}
                onChange={(e) =>
                  setForm((f) => ({ ...f, kitchen_length: e.target.value }))
                }
                placeholder="3.5"
              />
            </Field>

            <Field label="Waterfall ends" htmlFor="waterfall">
              <Input
                id="waterfall"
                type="number"
                min="0"
                max="2"
                value={form.waterfall}
                onChange={(e) => setForm((f) => ({ ...f, waterfall: e.target.value }))}
              />
            </Field>

            <Field label="Postcode (optional)" htmlFor="postcode">
              <Input
                id="postcode"
                value={form.postcode}
                onChange={(e) => setForm((f) => ({ ...f, postcode: e.target.value }))}
                placeholder="SW1A 1AA"
              />
            </Field>

            <div className="flex flex-col gap-2 sm:col-span-2 sm:flex-row sm:gap-6">
              <Checkbox
                label="Island"
                checked={form.island}
                onChange={(e) => setForm((f) => ({ ...f, island: e.target.checked }))}
              />
              <Checkbox
                label="Splashback"
                checked={form.splashback}
                onChange={(e) =>
                  setForm((f) => ({ ...f, splashback: e.target.checked }))
                }
              />
              <Checkbox
                label="Upstands"
                checked={form.upstands}
                onChange={(e) =>
                  setForm((f) => ({ ...f, upstands: e.target.checked }))
                }
              />
            </div>

            {error && (
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger sm:col-span-2">
                {error}
              </p>
            )}

            <div className="sm:col-span-2">
              <Button type="submit" disabled={submitting}>
                {submitting ? "Calculating…" : "Calculate Quote"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {result && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Quote for {result.customer}</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-muted">Material</dt>
              <dd className="text-right text-foreground">{result.material}</dd>
              <dt className="text-muted">Slabs required</dt>
              <dd className="text-right text-foreground">{result.slabs}</dd>
              <dt className="text-muted">Price per slab</dt>
              <dd className="text-right text-foreground">
                {formatCurrencyGBP(result.price_per_slab)}
              </dd>
              <dt className="text-muted">Subtotal</dt>
              <dd className="text-right text-foreground">
                {formatCurrencyGBP(result.price_before_vat)}
              </dd>
              <dt className="text-muted">VAT (20%)</dt>
              <dd className="text-right text-foreground">
                {formatCurrencyGBP(result.vat)}
              </dd>
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
