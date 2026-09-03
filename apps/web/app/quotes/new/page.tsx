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
  quantity: "1",
  length_mm: "",
  width_mm: "650",
  island: false,
  waterfall: "0",
  splashback: false,
  splashback_length_mm: "",
  upstands: false,
  upstands_length_mm: "",
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
  const [aiMatchStatus, setAiMatchStatus] = useState<string | null>(null);
  const [aiCandidates, setAiCandidates] = useState<string[]>([]);
  const [aiInterpreted, setAiInterpreted] = useState<string | null>(null);

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
        quantity: Number(form.quantity) || 1,
        length_mm: Number(form.length_mm) || 0,
        width_mm: Number(form.width_mm) || 650,
        unit_input: "mm",
        island: form.island,
        waterfall: Number(form.waterfall) || 0,
        splashback: form.splashback,
        splashback_length_mm: form.splashback ? Number(form.splashback_length_mm) || null : null,
        upstands: form.upstands,
        upstands_length_mm: form.upstands ? Number(form.upstands_length_mm) || null : null,
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
    setAiMatchStatus(null);
    setAiCandidates([]);
    setAiInterpreted(null);

    try {
      const draft = await api.generateQuoteDraft(aiText);

      // Pre-fills the existing manual form — never auto-submitted, never
      // priced here. The user reviews every field below before calculating.
      setForm((f) => ({
        ...f,
        customer: draft.customer ?? f.customer,
        material: draft.material ?? f.material,
        thickness: draft.thickness ?? f.thickness,
        quantity: draft.quantity !== null ? String(draft.quantity) : f.quantity,
        length_mm: draft.length_mm !== null ? String(draft.length_mm) : f.length_mm,
        width_mm: draft.width_mm !== null ? String(draft.width_mm) : f.width_mm,
        island: draft.island,
        waterfall: String(draft.waterfall),
        splashback: draft.splashback,
        upstands: draft.upstands,
        postcode: draft.postcode ?? f.postcode,
      }));
      setAiWarnings(draft.warnings);
      setAiMatchStatus(draft.material_match_status);
      setAiCandidates(draft.material_candidates);

      // Sprint 032 (Workstream C): the AI must show its interpreted
      // dimensions back to the user before/at quote creation, so an
      // incorrect parse is visible rather than silently trusted.
      if (draft.length_mm !== null) {
        const widthPart = draft.width_mm !== null ? ` x ${draft.width_mm}mm` : "";
        const qtyPart = draft.quantity && draft.quantity > 1 ? `${draft.quantity} x ` : "";
        const unitNote = draft.unit_input && draft.unit_input !== "mm"
          ? ` (entered as ${draft.unit_input})`
          : "";
        setAiInterpreted(`${qtyPart}${draft.length_mm}mm${widthPart}${unitNote}`);
      }
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
                placeholder="e.g. Calacatta Oro 20mm worktop, 2400 x 600mm, customer Sarah Whitfield"
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

            {aiInterpreted && (
              <p className="mt-3 rounded-lg bg-accent/10 px-3 py-2 text-sm text-foreground">
                Interpreted dimensions: <strong>{aiInterpreted}</strong> — check
                this against the form below before calculating.
              </p>
            )}

            {aiMatchStatus === "multiple" && aiCandidates.length > 0 && (
              <p className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-sm text-foreground">
                Matched more than one product — pick one manually:{" "}
                {aiCandidates.join(", ")}
              </p>
            )}

            {aiMatchStatus === "not_found" && (
              <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                No matching product was found in the SIMO OS catalogue — pick
                a material manually rather than guessing.
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

            <Field label="Quantity" htmlFor="quantity">
              <Input
                id="quantity"
                type="number"
                min="1"
                step="1"
                value={form.quantity}
                onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
              />
            </Field>

            <Field label="Length (mm)" htmlFor="length_mm">
              <Input
                id="length_mm"
                type="number"
                step="1"
                min="0"
                required
                value={form.length_mm}
                onChange={(e) => setForm((f) => ({ ...f, length_mm: e.target.value }))}
                placeholder="e.g. 2400"
              />
            </Field>

            <Field label="Width/Depth (mm)" htmlFor="width_mm">
              <Input
                id="width_mm"
                type="number"
                step="1"
                min="0"
                value={form.width_mm}
                onChange={(e) => setForm((f) => ({ ...f, width_mm: e.target.value }))}
                placeholder="e.g. 600 (standard worktop depth is 650mm)"
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

            {/* Sprint 032 (Workstream C): splashback/upstands each need
               their own length — never silently reuse the worktop run's
               length — so these only appear (and are required) once the
               corresponding checkbox is on. */}
            {form.splashback && (
              <Field label="Splashback length (mm)" htmlFor="splashback_length_mm">
                <Input
                  id="splashback_length_mm"
                  type="number"
                  step="1"
                  min="0"
                  required
                  value={form.splashback_length_mm}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, splashback_length_mm: e.target.value }))
                  }
                  placeholder="e.g. 3000"
                />
              </Field>
            )}

            {form.upstands && (
              <Field label="Upstand length (mm)" htmlFor="upstands_length_mm">
                <Input
                  id="upstands_length_mm"
                  type="number"
                  step="1"
                  min="0"
                  required
                  value={form.upstands_length_mm}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, upstands_length_mm: e.target.value }))
                  }
                  placeholder="e.g. 3000"
                />
              </Field>
            )}

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
              <dt className="text-muted">Dimensions</dt>
              <dd className="text-right text-foreground">
                {result.dimensions.quantity > 1 ? `${result.dimensions.quantity} x ` : ""}
                {result.dimensions.length_mm}mm x {result.dimensions.width_mm}mm
              </dd>
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
