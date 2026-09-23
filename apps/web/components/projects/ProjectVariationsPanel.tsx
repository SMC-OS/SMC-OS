"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { parseNumberInput } from "@/lib/number";
import { formatCurrencyGBP, formatDateTime } from "@/lib/utils";
import { VARIATION_STATUS_LABELS, VARIATION_STATUS_TONE } from "@/types/variation";
import type { Variation, VariationItemIn } from "@/types/variation";

const EMPTY_ITEM: VariationItemIn = { description: "", quantity: 1, unit: "item", unit_price: 0 };

/**
 * GeoCore Premium OS Plan 04 (Sprint 043), Task 15 — the variation
 * (change order) workspace: list, create a draft with line items, then
 * send/approve/reject/void it. Only the actions valid for the variation's
 * current status are ever shown (draft: edit/send/approve/reject/void;
 * sent: approve/reject/void; approved/rejected/void: terminal, PDF only).
 */
export function ProjectVariationsPanel({ projectId }: { projectId: string }) {
  const [variations, setVariations] = useState<Variation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<VariationItemIn[]>([{ ...EMPTY_ITEM }]);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    api
      .getProjectVariations(projectId)
      .then(setVariations)
      .catch(() => setError("Could not load variations."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  function updateItem(index: number, changes: Partial<VariationItemIn>) {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...changes } : item)));
  }

  async function createVariation(event: React.FormEvent) {
    event.preventDefault();
    const validItems = items.filter((item) => item.description.trim());
    if (!title.trim()) return;

    setSaving(true);
    setError(null);
    try {
      const created = await api.createVariation(projectId, {
        title: title.trim(),
        description: description.trim() || null,
        items: validItems,
      });
      setVariations((current) => [created, ...(current ?? [])]);
      setTitle("");
      setDescription("");
      setItems([{ ...EMPTY_ITEM }]);
      setShowForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the variation.");
    } finally {
      setSaving(false);
    }
  }

  async function transition(id: string, action: "send" | "approve" | "reject" | "void") {
    setBusyId(id);
    setError(null);
    try {
      const updated =
        action === "send"
          ? await api.sendVariation(id)
          : action === "approve"
            ? await api.approveVariation(id)
            : action === "reject"
              ? await api.rejectVariation(id)
              : await api.voidVariation(id);
      setVariations((current) => (current ?? []).map((v) => (v.id === id ? updated : v)));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 409
            ? "That action isn't available for this variation right now — try refreshing."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setBusyId(null);
    }
  }

  async function downloadPdf(variation: Variation) {
    setBusyId(variation.id);
    setError(null);
    try {
      await api.downloadVariationPdf(variation.id, variation.reference);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download the PDF.");
    } finally {
      setBusyId(null);
    }
  }

  if (!variations) {
    return (
      <div>
        {error && <p className="mb-3 text-sm text-danger">{error}</p>}
        {!error && <p className="text-sm text-muted">Loading…</p>}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-danger">{error}</p>}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Variations</CardTitle>
          {!showForm && (
            <Button size="sm" onClick={() => setShowForm(true)}>
              <PlusIcon className="h-4 w-4" />
              New variation
            </Button>
          )}
        </CardHeader>
        <CardContent className="pt-4">
          {showForm && (
            <form onSubmit={createVariation} className="mb-4 rounded-lg border border-border p-4">
              <div className="grid grid-cols-1 gap-3">
                <Field label="Title" htmlFor="variationTitle">
                  <Input
                    id="variationTitle"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Additional bathroom tiling"
                  />
                </Field>
                <Field label="Description" htmlFor="variationDescription">
                  <Textarea
                    id="variationDescription"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </Field>
              </div>

              <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-muted">
                Items
              </p>
              <div className="space-y-3">
                {items.map((item, index) => (
                  <div key={index} className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                    <Input
                      className="sm:col-span-2"
                      aria-label="Item description"
                      placeholder="Description"
                      value={item.description}
                      onChange={(e) => updateItem(index, { description: e.target.value })}
                    />
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      aria-label="Quantity"
                      placeholder="Qty"
                      value={item.quantity}
                      onChange={(e) => updateItem(index, { quantity: parseNumberInput(e.target.value) })}
                    />
                    <Input
                      aria-label="Unit"
                      placeholder="Unit"
                      value={item.unit}
                      onChange={(e) => updateItem(index, { unit: e.target.value })}
                    />
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      aria-label="Unit price"
                      placeholder="Unit price"
                      value={item.unit_price}
                      onChange={(e) => updateItem(index, { unit_price: parseNumberInput(e.target.value) })}
                    />
                  </div>
                ))}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => setItems((current) => [...current, { ...EMPTY_ITEM }])}
              >
                <PlusIcon className="h-4 w-4" />
                Add item
              </Button>

              <div className="mt-4 flex gap-2">
                <Button type="submit" disabled={saving || !title.trim()}>
                  {saving ? "Saving…" : "Save draft"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {variations.length === 0 ? (
            <EmptyState
              title="No variations yet"
              description="Create a draft to capture a change to this project's scope."
              className="py-8"
            />
          ) : (
            <ul className="divide-y divide-border border-t border-border">
              {variations.map((variation) => (
                <li key={variation.id} className="py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {variation.reference} &middot; {variation.title}
                      </p>
                      <p className="text-xs text-muted">
                        {formatCurrencyGBP(variation.total)} total
                        {variation.approved_at
                          ? ` · Approved ${formatDateTime(variation.approved_at)}`
                          : ""}
                      </p>
                    </div>
                    <Badge tone={VARIATION_STATUS_TONE[variation.status]}>
                      {VARIATION_STATUS_LABELS[variation.status]}
                    </Badge>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {(variation.status === "draft" || variation.status === "sent") && (
                      <>
                        {variation.status === "draft" && (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={busyId === variation.id}
                            onClick={() => transition(variation.id, "send")}
                          >
                            Send
                          </Button>
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busyId === variation.id}
                          onClick={() => transition(variation.id, "approve")}
                        >
                          Approve
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busyId === variation.id}
                          onClick={() => transition(variation.id, "reject")}
                        >
                          Reject
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busyId === variation.id}
                          onClick={() => transition(variation.id, "void")}
                          aria-label={`Void ${variation.reference}`}
                        >
                          <TrashIcon className="h-4 w-4" />
                          Void
                        </Button>
                      </>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busyId === variation.id}
                      onClick={() => downloadPdf(variation)}
                    >
                      Download PDF
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
