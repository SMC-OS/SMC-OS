"use client";

import Link from "next/link";
import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Checkbox, Field, Input, Select } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP } from "@/lib/utils";
import { MATERIAL_OPTIONS, THICKNESS_OPTIONS, type QuoteResult } from "@/types/quote";

const initialForm = {
  customer: "",
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
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QuoteResult | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const quote = await api.createQuote({
        customer: form.customer || "Unknown",
        material: form.material,
        thickness: form.thickness,
        kitchen_length: Number(form.kitchen_length) || 0,
        island: form.island,
        waterfall: Number(form.waterfall) || 0,
        splashback: form.splashback,
        upstands: form.upstands,
        postcode: form.postcode || undefined,
      });

      setResult(quote);

      // Surface this in Recent Activity on the dashboard — same backend
      // endpoint the dashboard already polls.
      api
        .logActivity({
          type: "quote_created",
          title: `New quote created`,
          description: `${quote.customer} — ${quote.material}, ${formatCurrencyGBP(quote.total)}`,
        })
        .catch(() => {
          /* non-critical: the quote itself already succeeded */
        });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
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
          Calculated live by the existing quote engine (POST /quote) — pricing
          uses the full material catalogue, thickness included.
        </p>
      </div>

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
          </CardContent>
        </Card>
      )}
    </div>
  );
}
