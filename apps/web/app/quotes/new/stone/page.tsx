"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, useSyncExternalStore } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select } from "@/components/ui/Field";
import {
  ExtrasPicker,
  blankDesignDetails,
  type DesignDetails,
} from "@/components/quotes/ExtrasPicker";
import {
  LayoutPicker,
  planPieces,
  type WorktopPiece,
} from "@/components/quotes/LayoutPicker";
import { MaterialCatalogueSearch } from "@/components/quotes/MaterialCatalogueSearch";
import { ApiError, api } from "@/lib/api";
import { readQuoteCustomMaterial } from "@/lib/quote-custom-material";
import type { CustomMaterialInput } from "@/types/catalogue";
import { formatCurrencyGBP } from "@/lib/utils";
import {
  EXTRA_LABELS,
  ITEM_TYPE_LABELS,
  ITEM_TYPES,
  LAYOUT_LABELS,
  MATERIAL_OPTIONS,
  THICKNESS_OPTIONS,
  type AIQuoteItemDraft,
  type ExtraOption,
  type ItemType,
  type LayoutOption,
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
  // Sprint 042 (GeoCore Premium OS Plan 03) — set when this row was
  // populated from the Master Catalogue (via /catalogue's "Use in a
  // stone quote"), rather than typed as free text. Cleared the moment
  // the material/thickness fields are hand-edited, since at that point
  // they no longer describe the catalogue surface.
  catalogue_surface_id: string | null;
  catalogue_variant_id: string | null;
  // A layout expands into separately measured quote lines on submission.
  custom_material: CustomMaterialInput | null;
  layout: LayoutOption | "";
  extras: ExtraOption[];
  pieces: WorktopPiece[];
  designDetails: DesignDetails;
  drawing: { id: string; filename: string } | null;
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
    catalogue_surface_id: null,
    catalogue_variant_id: null,
    custom_material: null,
    layout: "",
    extras: [],
    designDetails: blankDesignDetails(),
    drawing: null,
    pieces: ["B", "C", "D"].map((label) => ({
      label,
      length: "",
      width: "650",
    })),
    ...overrides,
  };
}

/** Post-release remediation §4 — layout/extras are UI-only concepts with
 * no backend column of their own; they're folded into the existing free-
 * text `notes` field so they persist and print on the quote without any
 * schema change. */
function composeItemNotes(row: ItemRow): string | null {
  const parts: string[] = [];
  if (row.drawing)
    parts.push(
      `Drawing: ${row.drawing.filename} (customer document ${row.drawing.id})`,
    );
  if (row.layout) parts.push(`Layout: ${LAYOUT_LABELS[row.layout]}`);
  if (row.extras.length > 0)
    parts.push(`Extras: ${row.extras.map((e) => EXTRA_LABELS[e]).join(", ")}`);
  if (row.extras.includes("cutout")) {
    if (row.designDetails.sink) parts.push(`Sink: ${row.designDetails.sink}`);
    if (row.designDetails.hob)
      parts.push(`Hob cut-outs: ${row.designDetails.hob}`);
    if (row.designDetails.taps)
      parts.push(`Tap holes: ${row.designDetails.taps}`);
  }
  if (row.extras.includes("upstand_included"))
    parts.push(
      `Upstand: ${row.designDetails.upstandLength} × ${row.designDetails.upstandHeight} mm`,
    );
  if (row.extras.includes("splashback_included"))
    parts.push(
      `Splashback: ${row.designDetails.splashbackLength} × ${row.designDetails.splashbackHeight} mm`,
    );
  return parts.length > 0 ? parts.join(". ") : null;
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
  return (
    <Suspense fallback={null}>
      <NewQuotePageEntry />
    </Suspense>
  );
}

// Resolve browser draft data before mounting the editor. No post-mount
// setState overwrites the user's edits, and SSR never reads tab storage.
const subscribeHydration = () => () => {};
function NewQuotePageEntry() {
  const searchParams = useSearchParams();
  const ready = useSyncExternalStore(
    subscribeHydration,
    () => true,
    () => false,
  );
  if (!ready) return <p role="status">Loading quote editor…</p>;
  let initialItem: Partial<ItemRow> = {};
  let initialError: string | null = null;
  const customId = searchParams.get("custom_material_id");
  if (customId) {
    try {
      const custom = readQuoteCustomMaterial(customId);
      initialItem = {
        material: custom.canonical_name,
        thickness: custom.variant?.thickness_mm
          ? `${custom.variant.thickness_mm}mm`
          : "20mm",
        custom_material: custom,
      };
    } catch (err) {
      initialError =
        err instanceof Error
          ? err.message
          : "This custom material draft could not be loaded.";
    }
  } else if (searchParams.get("catalogue_surface_id")) {
    initialItem = {
      catalogue_surface_id: searchParams.get("catalogue_surface_id"),
      catalogue_variant_id: searchParams.get("catalogue_variant_id"),
      material: searchParams.get("material") ?? MATERIAL_OPTIONS[0],
      thickness: searchParams.get("thickness") ?? THICKNESS_OPTIONS[0],
    };
  }
  return (
    <NewQuotePageInner
      key={searchParams.toString()}
      initialItem={initialItem}
      initialError={initialError}
      initialCustomerId={searchParams.get("customer") ?? ""}
    />
  );
}

function NewQuotePageInner({
  initialItem,
  initialError,
  initialCustomerId,
}: {
  initialItem: Partial<ItemRow>;
  initialError: string | null;
  initialCustomerId: string;
}) {
  const { isAuthenticated } = useAuth();
  const [step, setStep] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const stepNames = ["Material", "Layout", "Design details", "Review"];
  const showStep = (index: number) => showAll || step === index;
  const [customer, setCustomer] = useState("");
  const [customerId, setCustomerId] = useState(initialCustomerId);
  const [postcode, setPostcode] = useState("");
  const [items, setItems] = useState<ItemRow[]>(() => [blankItem(initialItem)]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const customMaterialError = initialError;
  const [result, setResult] = useState<QuoteResult | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [uploadingKey, setUploadingKey] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // AI Quotation Generator — separate state from the manual form's
  // submitting/error, so an AI failure is never confused with a
  // calculation failure, and the manual form stays usable regardless.
  const [aiText, setAiText] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiDraftItems, setAiDraftItems] = useState<AIQuoteItemDraft[] | null>(
    null,
  );
  const [aiWarnings, setAiWarnings] = useState<string[]>([]);

  useEffect(() => {
    if (!isAuthenticated) return;
    api
      .getCustomers()
      .then(async (rows) => {
        setCustomers(rows);
        const selected = rows.find((row) => row.id === initialCustomerId);
        if (selected) {
          setCustomer(selected.name);
        } else if (initialCustomerId) {
          try {
            const initialCustomer = await api.getCustomer(initialCustomerId);
            setCustomers([...rows, initialCustomer]);
            setCustomer(initialCustomer.name);
          } catch {}
        }
      })
      .catch(() => {});
  }, [isAuthenticated, initialCustomerId]);

  function handleCustomerSelect(id: string) {
    const selected = customers.find((c) => c.id === id);
    setCustomerId(id);
    setItems((rows) => rows.map((row) => ({ ...row, drawing: null })));
    setResult(null);
    if (selected) setCustomer(selected.name);
  }

  function updateItem(key: string, patch: Partial<ItemRow>) {
    setResult(null);
    setItems((rows) =>
      rows.map((r) => (r.key === key ? { ...r, ...patch } : r)),
    );
  }

  async function uploadDrawing(key: string, file: File) {
    if (!customerId) return;
    setUploadError(null);
    if (!/\.(pdf|png|jpe?g)$/i.test(file.name) || file.size > 5 * 1024 * 1024) {
      setUploadError("Choose a PDF, JPG or PNG drawing up to 5 MB.");
      return;
    }
    setUploadingKey(key);
    try {
      const document = await api.uploadDocument(customerId, file);
      updateItem(key, { drawing: { id: document.id, filename: file.name } });
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : "Drawing upload failed. Try again.",
      );
    } finally {
      setUploadingKey(null);
    }
  }

  function addItem() {
    setResult(null);
    setItems((rows) => [...rows, blankItem()]);
  }

  function removeItem(key: string) {
    setResult(null);
    setItems((rows) =>
      rows.length > 1 ? rows.filter((r) => r.key !== key) : rows,
    );
  }

  function duplicateItem(key: string) {
    setResult(null);
    setItems((rows) => {
      const index = rows.findIndex((r) => r.key === key);
      if (index === -1) return rows;
      const copy = {
        ...rows[index],
        key: newRowKey(),
        pieces: rows[index].pieces.map((piece) => ({ ...piece })),
        designDetails: { ...rows[index].designDetails },
      };
      return [...rows.slice(0, index + 1), copy, ...rows.slice(index + 1)];
    });
  }

  function moveItem(key: string, direction: -1 | 1) {
    setResult(null);
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
    if (uploadingKey) return;
    if (!showAll && step < 3) {
      setStep(step + 1);
      return;
    }
    if (
      !customer.trim() ||
      items.some(
        (row) =>
          !row.material.trim() ||
          !Number.isInteger(Number(row.quantity)) ||
          Number(row.quantity) < 1 ||
          Number(row.length_mm) <= 0 ||
          Number(row.width_mm) <= 0 ||
          (["upstand", "splashback"] as const).some(
            (kind) =>
              row.extras.includes(
                kind === "upstand" ? "upstand_included" : "splashback_included",
              ) &&
              (Number(row.designDetails[`${kind}Length`]) <= 0 ||
                Number(row.designDetails[`${kind}Height`]) <= 0),
          ) ||
          (row.layout &&
            planPieces(row.layout)
              .slice(1)
              .some((piece) => {
                const measured = row.pieces.find(
                  (p) => p.label === piece.label,
                );
                return (
                  !measured ||
                  Number(measured.length) <= 0 ||
                  Number(measured.width) <= 0
                );
              })),
      )
    ) {
      setError(
        "Complete the customer, material and positive measurements for every piece before calculating.",
      );
      return;
    }
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const quote = await api.createQuote({
        customer: customer || "Unknown",
        customer_id: customerId || null,
        postcode: postcode || undefined,
        items: items.flatMap((row) => {
          const pieces = row.layout
            ? planPieces(row.layout)
            : [{ label: "A", island: false }];
          return [
            ...pieces.map((piece) => {
              const measured = row.pieces.find((p) => p.label === piece.label);
              return {
                item_type: piece.island ? "island" : row.item_type,
                material: row.material,
                thickness: row.thickness,
                quantity: Number(row.quantity) || 1,
                length_mm:
                  Number(
                    piece.label === "A" ? row.length_mm : measured?.length,
                  ) || 0,
                width_mm:
                  Number(
                    piece.label === "A" ? row.width_mm : measured?.width,
                  ) || 650,
                slab_group: row.layout ? row.key : undefined,
                unit_input: "mm" as const,
                custom_material: row.custom_material,
                catalogue_surface_id: row.catalogue_surface_id,
                catalogue_variant_id: row.catalogue_variant_id,
                notes:
                  [
                    row.layout ? `Piece ${piece.label}` : null,
                    composeItemNotes(row),
                  ]
                    .filter(Boolean)
                    .join(". ") || null,
              };
            }),
            ...(["upstand", "splashback"] as const)
              .filter((kind) =>
                row.extras.includes(
                  kind === "upstand"
                    ? "upstand_included"
                    : "splashback_included",
                ),
              )
              .map((kind) => ({
                item_type: kind,
                material: row.material,
                thickness: row.thickness,
                quantity: Number(row.quantity),
                length_mm: Number(row.designDetails[`${kind}Length`]),
                width_mm: Number(row.designDetails[`${kind}Height`]),
                slab_group: row.layout ? row.key : undefined,
                unit_input: "mm" as const,
                custom_material: row.custom_material,
                catalogue_surface_id: row.catalogue_surface_id,
                catalogue_variant_id: row.catalogue_variant_id,
                notes: `Measured ${kind} for ${row.material}`,
              })),
          ];
        }),
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
          : "Something went wrong.",
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
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not download the invoice.",
      );
    } finally {
      setDownloading(false);
    }
  }

  if (customMaterialError)
    return (
      <Card>
        <CardContent className="py-6">
          <p role="alert">{customMaterialError}</p>
          <Link href="/catalogue" className="mt-4 inline-block underline">
            Return to the Catalogue
          </Link>
        </CardContent>
      </Card>
    );

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6">
        <Link
          href="/quotes/new"
          className="tap-link text-sm text-muted hover:text-foreground"
        >
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
          <Link
            href="/quotes/new"
            className="tap-link font-medium text-accent hover:underline"
          >
            Use the general construction quote
          </Link>
          .
        </p>
      </div>

      {isAuthenticated && (
        <details className="mb-6">
          <summary className="cursor-pointer rounded-xl border border-border px-4 py-3 text-sm font-medium text-foreground">
            Draft with AI (optional)
          </summary>
          <Card className="mt-3">
            <CardHeader>
              <CardTitle>Draft with AI</CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              <p className="mb-3 text-sm text-muted">
                Describe the job in plain text — this only pre-fills the items
                below for you to review. It never submits or prices anything.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row">
                {/* Sprint 036 (Workstream M) — this textarea shipped with
                  no label of any kind: a screen reader announced an
                  unnamed edit field. The visible heading above is the
                  card title, which is not an accessible name. */}
                <label htmlFor="aiDraftText" className="sr-only">
                  Describe the job for the AI to draft
                </label>
                <textarea
                  id="aiDraftText"
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
                    Interpreted {aiDraftItems.length} item
                    {aiDraftItems.length > 1 ? "s" : ""} — check these before
                    adding to the quote:
                  </p>
                  <ul className="flex flex-col gap-2">
                    {aiDraftItems.map((item, i) => (
                      <li
                        key={i}
                        className="rounded-md bg-surface-hover px-3 py-2 text-sm"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-foreground">
                            {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
                          </span>
                          {item.material_match_status === "found" && (
                            <Badge tone="success">{item.material}</Badge>
                          )}
                          {item.material_match_status === "multiple" && (
                            <Badge tone="warning">
                              Ambiguous — pick manually
                            </Badge>
                          )}
                          {item.material_match_status === "not_found" && (
                            <Badge tone="danger">
                              Not found: {item.material_raw}
                            </Badge>
                          )}
                          {item.material_match_status === null && (
                            <Badge tone="neutral">No material stated</Badge>
                          )}
                        </div>
                        <p className="mt-1 text-xs text-muted">
                          {item.quantity ?? 1} x{" "}
                          {item.length_mm !== null
                            ? `${item.length_mm}mm`
                            : "? length"}{" "}
                          x{" "}
                          {item.width_mm !== null
                            ? `${item.width_mm}mm`
                            : "? width"}
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
                          <p className="mt-1 text-xs text-warning">
                            {item.warnings.join(" ")}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                  <Button
                    type="button"
                    size="sm"
                    className="mt-3"
                    onClick={applyAiDraft}
                  >
                    Use these items
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </details>
      )}

      <nav aria-label="Quote steps" className="mb-5 grid grid-cols-4 gap-2">
        {stepNames.map((name, index) => (
          <div
            key={name}
            aria-current={!showAll && step === index ? "step" : undefined}
            className={`rounded-lg border px-2 py-3 text-center text-xs sm:text-sm ${step === index && !showAll ? "border-accent bg-accent/10 text-accent" : "border-border text-muted"}`}
          >
            <span className="mb-1 block font-semibold">{index + 1}</span>
            {name}
          </div>
        ))}
      </nav>
      <label className="mb-5 flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={showAll}
          onChange={(event) => setShowAll(event.target.checked)}
        />{" "}
        Show all sections
      </label>
      <form onSubmit={handleSubmit}>
        <fieldset disabled={!showStep(0)} hidden={!showStep(0)}>
          <h2 className="mb-4 text-xl font-semibold">
            1. Material &amp; customer
          </h2>
          <Card className="mb-6">
            <CardContent>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field
                  label="Customer name"
                  htmlFor="customer"
                  className="sm:col-span-2"
                >
                  <Input
                    id="customer"
                    required
                    value={customer}
                    onChange={(e) => {
                      setCustomer(e.target.value);
                      setResult(null);
                    }}
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
                      disabled={uploadingKey !== null}
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
                    onChange={(e) => {
                      setPostcode(e.target.value);
                      setResult(null);
                    }}
                    placeholder="e.g. AB1 2CD"
                  />
                </Field>
              </div>
            </CardContent>
          </Card>
        </fieldset>
        <div className="flex flex-col gap-4" hidden={!showAll && step === 3}>
          {items.map((row, index) => (
            <Card key={row.key}>
              <CardContent className="pt-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted">
                    Item {index + 1}
                    {row.catalogue_surface_id && (
                      <Badge tone="accent">From catalogue</Badge>
                    )}
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

                <fieldset disabled={!showStep(0)} hidden={!showStep(0)}>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="Type" htmlFor={`${row.key}-type`}>
                      <Select
                        id={`${row.key}-type`}
                        value={row.item_type}
                        onChange={(e) =>
                          updateItem(row.key, {
                            item_type: e.target.value as ItemType,
                          })
                        }
                      >
                        {ITEM_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {ITEM_TYPE_LABELS[t]}
                          </option>
                        ))}
                      </Select>
                    </Field>

                    {row.catalogue_surface_id || row.custom_material ? (
                      <Field label="Material" htmlFor={`${row.key}-material`}>
                        <div className="flex h-10 items-center justify-between gap-2 rounded-lg border border-border bg-surface-hover px-3 text-sm text-foreground">
                          <span className="truncate" id={`${row.key}-material`}>
                            {row.material}
                          </span>
                          <button
                            type="button"
                            className="tap-link shrink-0 text-xs text-accent hover:underline"
                            onClick={() =>
                              updateItem(row.key, {
                                custom_material: null,
                                catalogue_surface_id: null,
                                catalogue_variant_id: null,
                                material: MATERIAL_OPTIONS[0],
                              })
                            }
                          >
                            Change
                          </button>
                        </div>
                      </Field>
                    ) : (
                      <Field label="Material" htmlFor={`${row.key}-material`}>
                        <MaterialCatalogueSearch
                          id={`${row.key}-material`}
                          value={row.material}
                          onFreeTextChange={(text) =>
                            updateItem(row.key, { material: text })
                          }
                          onSelectSurface={(
                            surface,
                            thicknessLabel,
                            variantId,
                          ) =>
                            updateItem(row.key, {
                              material: surface.canonical_name,
                              thickness: thicknessLabel,
                              catalogue_surface_id: surface.id,
                              catalogue_variant_id: variantId,
                            })
                          }
                        />
                      </Field>
                    )}

                    <Field label="Thickness" htmlFor={`${row.key}-thickness`}>
                      {row.catalogue_surface_id || row.custom_material ? (
                        <div className="flex h-10 items-center rounded-lg border border-border bg-surface-hover px-3 text-sm text-foreground">
                          {row.thickness}
                        </div>
                      ) : (
                        <Select
                          id={`${row.key}-thickness`}
                          value={row.thickness}
                          onChange={(e) =>
                            updateItem(row.key, { thickness: e.target.value })
                          }
                        >
                          {THICKNESS_OPTIONS.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </Select>
                      )}
                    </Field>
                  </div>
                </fieldset>
                <fieldset disabled={!showStep(1)} hidden={!showStep(1)}>
                  <div className="mt-6 border-t border-border pt-5">
                    <h2 className="mb-3 text-lg font-semibold">
                      2. Worktop layout &amp; measurements
                    </h2>
                    <LayoutPicker
                      idPrefix={row.key}
                      value={row.layout}
                      onChange={(layout) => updateItem(row.key, { layout })}
                    />
                  </div>
                  <fieldset className="mt-4 rounded-xl border border-border p-4">
                    <legend className="px-2 font-semibold">
                      {row.layout ? "Piece A" : "Piece measurements"}
                    </legend>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      <Field label="Quantity" htmlFor={`${row.key}-qty`}>
                        <Input
                          id={`${row.key}-qty`}
                          type="number"
                          min="1"
                          step="1"
                          value={row.quantity}
                          onChange={(e) =>
                            updateItem(row.key, { quantity: e.target.value })
                          }
                        />
                      </Field>

                      <Field label="Length (mm)" htmlFor={`${row.key}-length`}>
                        <Input
                          id={`${row.key}-length`}
                          type="number"
                          step="1"
                          min="1"
                          required
                          value={row.length_mm}
                          onChange={(e) =>
                            updateItem(row.key, { length_mm: e.target.value })
                          }
                          placeholder="e.g. 2400"
                        />
                      </Field>

                      <Field
                        label="Width/Depth (mm)"
                        htmlFor={`${row.key}-width`}
                      >
                        <Input
                          id={`${row.key}-width`}
                          required
                          type="number"
                          step="1"
                          min="1"
                          value={row.width_mm}
                          onChange={(e) =>
                            updateItem(row.key, { width_mm: e.target.value })
                          }
                          placeholder="e.g. 600"
                        />
                      </Field>
                    </div>
                  </fieldset>
                  <div className="mt-4">
                    {row.layout && (
                      <p className="mt-4 text-sm text-muted">
                        Enter the finished size of each piece. Measurements are
                        in millimetres. Pieces in this layout share a
                        material-area estimate including 15% waste. This is not
                        a cutting or grain-matching plan; review slab fit before
                        issuing a final price.
                      </p>
                    )}
                    {row.layout &&
                      planPieces(row.layout)
                        .slice(1)
                        .map((piece) => {
                          const measured = row.pieces.find(
                            (p) => p.label === piece.label,
                          )!;
                          return (
                            <fieldset
                              key={piece.label}
                              className="mt-4 rounded-xl border border-border p-4"
                            >
                              <legend className="px-2 font-semibold">
                                Piece {piece.label}
                                {piece.island ? " · Island" : ""}
                              </legend>
                              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                <Field
                                  label={`Piece ${piece.label} length (mm)`}
                                  htmlFor={`${row.key}-${piece.label}-length`}
                                >
                                  <Input
                                    id={`${row.key}-${piece.label}-length`}
                                    type="number"
                                    inputMode="numeric"
                                    min="1"
                                    step="1"
                                    required
                                    value={measured.length}
                                    onChange={(event) =>
                                      updateItem(row.key, {
                                        pieces: row.pieces.map((p) =>
                                          p.label === piece.label
                                            ? {
                                                ...p,
                                                length: event.target.value,
                                              }
                                            : p,
                                        ),
                                      })
                                    }
                                  />
                                </Field>
                                <Field
                                  label={`Piece ${piece.label} width (mm)`}
                                  htmlFor={`${row.key}-${piece.label}-width`}
                                >
                                  <Input
                                    id={`${row.key}-${piece.label}-width`}
                                    type="number"
                                    inputMode="numeric"
                                    min="1"
                                    step="1"
                                    required
                                    value={measured.width}
                                    onChange={(event) =>
                                      updateItem(row.key, {
                                        pieces: row.pieces.map((p) =>
                                          p.label === piece.label
                                            ? {
                                                ...p,
                                                width: event.target.value,
                                              }
                                            : p,
                                        ),
                                      })
                                    }
                                  />
                                </Field>
                              </div>
                            </fieldset>
                          );
                        })}
                  </div>
                  <div className="mt-5 rounded-xl border border-dashed border-border p-4">
                    <Field
                      label="Upload layout drawing (optional)"
                      htmlFor={`${row.key}-drawing`}
                      hint="PDF, JPG or PNG, up to 5 MB. Saved to the linked customer’s documents and referenced in this quote."
                    >
                      <Input
                        id={`${row.key}-drawing`}
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png"
                        disabled={!customerId || uploadingKey !== null}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          if (file) void uploadDrawing(row.key, file);
                          event.target.value = "";
                        }}
                      />
                    </Field>
                    {!customerId && (
                      <p className="mt-2 text-sm text-muted">
                        Link an existing customer in step 1 to save a drawing.
                      </p>
                    )}
                    {uploadingKey === row.key && (
                      <p role="status" className="mt-2 text-sm">
                        Saving drawing…
                      </p>
                    )}
                    {row.drawing && (
                      <p role="status" className="mt-2 text-sm text-accent">
                        Saved drawing: {row.drawing.filename}
                      </p>
                    )}
                    {uploadError && (
                      <p role="alert" className="mt-2 text-sm text-danger">
                        {uploadError}
                      </p>
                    )}
                  </div>
                </fieldset>
                <fieldset disabled={!showStep(2)} hidden={!showStep(2)}>
                  <div className="mt-6 border-t border-border pt-5">
                    <h2 className="mb-3 text-lg font-semibold">
                      3. Design details
                    </h2>
                    <ExtrasPicker
                      idPrefix={row.key}
                      value={row.extras}
                      onChange={(extras) => updateItem(row.key, { extras })}
                      details={row.designDetails}
                      onDetailsChange={(designDetails) =>
                        updateItem(row.key, { designDetails })
                      }
                    />
                    <p className="mt-3 text-sm text-muted">
                      Measured upstands and splashbacks are priced as separate
                      lines. Cut-out, tap-hole and polished-edge charges need
                      review and are not added automatically.
                    </p>
                  </div>
                </fieldset>
              </CardContent>
            </Card>
          ))}
        </div>

        {showStep(3) && (
          <Card className="mt-5">
            <CardContent>
              <h2 className="mb-4 text-xl font-semibold">
                4. Review your quote
              </h2>
              <p className="mb-4 text-sm text-muted">
                {customer || "Customer not entered"}
                {postcode ? ` · ${postcode}` : ""}
              </p>
              <ul className="space-y-4">
                {items.map((row, index) => (
                  <li
                    key={row.key}
                    className="rounded-xl border border-border p-4"
                  >
                    <h3 className="font-semibold">
                      Item {index + 1}: {row.material} · {row.thickness}
                    </h3>
                    <p className="mt-1 text-sm text-muted">
                      {row.layout
                        ? LAYOUT_LABELS[row.layout]
                        : ITEM_TYPE_LABELS[row.item_type]}{" "}
                      · quantity {row.quantity}
                    </p>
                    <p className="mt-2 text-sm">
                      Piece A: {row.length_mm || "?"} × {row.width_mm || "?"} mm
                    </p>
                    {row.layout &&
                      planPieces(row.layout)
                        .slice(1)
                        .map((piece) => {
                          const measured = row.pieces.find(
                            (p) => p.label === piece.label,
                          );
                          return (
                            <p key={piece.label} className="text-sm">
                              Piece {piece.label}
                              {piece.island ? " (island)" : ""}:{" "}
                              {measured?.length || "?"} ×{" "}
                              {measured?.width || "?"} mm
                            </p>
                          );
                        })}
                    {composeItemNotes(row) && (
                      <p className="mt-2 text-sm text-muted">
                        {composeItemNotes(row)}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-sm text-muted">
                The estimate uses your catalogue prices and pools the material
                area of each selected layout, including 15% waste. Review the
                cutting plan before issuing a final price. Measured upstands and
                splashbacks add separate lines. Cut-out, tap-hole and
                polished-edge selections are specifications only. Calculating
                creates a saved quote; it does not send it to the customer.
              </p>
            </CardContent>
          </Card>
        )}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={addItem}>
              + Add item
            </Button>
            {isAuthenticated && (
              <Link href="/catalogue">
                <Button type="button" variant="ghost">
                  Browse Master Catalogue
                </Button>
              </Link>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {!showAll && step > 0 && (
              <Button
                variant="outline"
                onClick={() => {
                  setStep(step - 1);
                  setError(null);
                }}
              >
                Previous
              </Button>
            )}
            {!showAll && step < 3 ? (
              <Button
                type="button"
                onClick={(event) => {
                  if (event.currentTarget.form?.reportValidity()) {
                    setStep(step + 1);
                    setError(null);
                  }
                }}
              >
                Next: {stepNames[step + 1]}
              </Button>
            ) : (
              <Button
                type="submit"
                disabled={submitting || uploadingKey !== null}
              >
                {submitting ? "Calculating…" : "Calculate Quote"}
              </Button>
            )}
          </div>
        </div>

        {error && (
          <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </p>
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
                      {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type} —{" "}
                      {item.material} ({item.thickness})
                    </p>
                    <p className="text-xs text-muted">
                      {item.quantity} x {item.length_mm}mm x {item.width_mm}mm ·{" "}
                      {item.slab_allocation
                        ? `shares ${item.slab_allocation.group_slabs} slab${item.slab_allocation.group_slabs === 1 ? "" : "s"} across the layout`
                        : `${item.slabs} slab${item.slabs === 1 ? "" : "s"}`}
                    </p>
                    {item.notes && (
                      <p className="mt-1 text-xs text-muted">{item.notes}</p>
                    )}
                  </div>
                  <span className="text-foreground">
                    {item.line_total !== null
                      ? formatCurrencyGBP(item.line_total)
                      : "—"}
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
                <Button
                  onClick={handleDownload}
                  disabled={downloading}
                  variant="outline"
                >
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
