"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP, formatDate, formatDateTime } from "@/lib/utils";
import {
  REQUIREMENT_STATUS_LABELS,
  REQUIREMENT_STATUS_TONE,
  PO_STATUS_LABELS,
  PO_STATUS_TONE,
} from "@/types/procurement";
import type {
  CatalogueSupplierSummary,
  MaterialRequirement,
  MaterialRequirementIn,
  PurchaseOrder,
  PurchaseOrderItemIn,
  PurchaseReceiptItemIn,
} from "@/types/procurement";

const EMPTY_REQUIREMENT: MaterialRequirementIn = {
  description: "",
  required_quantity: null,
  unit: null,
  required_by_date: null,
};

const EMPTY_PO_ITEM: PurchaseOrderItemIn = {
  description: "",
  quantity: 1,
  unit: "item",
  unit_cost: 0,
};

/**
 * GeoCore Premium OS Plan 05 (Sprint 044), Task 21-24 — the project's
 * materials workspace: what's required, the purchase orders raised
 * against it, and recording deliveries as they arrive. Requirement and
 * PO status are always the backend's own derived state — this panel
 * never computes or guesses either.
 */
export function ProjectMaterialsPanel({ projectId }: { projectId: string }) {
  const [requirements, setRequirements] = useState<MaterialRequirement[] | null>(null);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[] | null>(null);
  const [suppliers, setSuppliers] = useState<CatalogueSupplierSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [showRequirementForm, setShowRequirementForm] = useState(false);
  const [requirement, setRequirement] = useState<MaterialRequirementIn>({ ...EMPTY_REQUIREMENT });
  const [savingRequirement, setSavingRequirement] = useState(false);

  const [showPoForm, setShowPoForm] = useState(false);
  const [poSupplierId, setPoSupplierId] = useState("");
  const [poExpectedDate, setPoExpectedDate] = useState("");
  const [poItems, setPoItems] = useState<PurchaseOrderItemIn[]>([{ ...EMPTY_PO_ITEM }]);
  const [savingPo, setSavingPo] = useState(false);

  const [receiptForId, setReceiptForId] = useState<string | null>(null);
  const [receiptQuantities, setReceiptQuantities] = useState<Record<string, number>>({});
  const [receiptReference, setReceiptReference] = useState("");
  const [savingReceipt, setSavingReceipt] = useState(false);

  const [orderingId, setOrderingId] = useState<string | null>(null);
  const [orderSupplierReference, setOrderSupplierReference] = useState("");
  const [orderExpectedDate, setOrderExpectedDate] = useState("");

  function load() {
    api
      .getProjectRequirements(projectId)
      .then(setRequirements)
      .catch(() => setError("Could not load material requirements."));
    api
      .getPurchaseOrders({ projectId })
      .then(setPurchaseOrders)
      .catch(() => setError("Could not load purchase orders."));
    api.getSuppliers().then(setSuppliers).catch(() => {});
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function createRequirement(event: React.FormEvent) {
    event.preventDefault();
    if (!requirement.description.trim()) return;
    setSavingRequirement(true);
    setError(null);
    try {
      const created = await api.createProjectRequirement(projectId, {
        ...requirement,
        description: requirement.description.trim(),
      });
      setRequirements((current) => [created, ...(current ?? [])]);
      setRequirement({ ...EMPTY_REQUIREMENT });
      setShowRequirementForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the requirement.");
    } finally {
      setSavingRequirement(false);
    }
  }

  async function cancelRequirement(id: string) {
    setBusyId(id);
    setError(null);
    try {
      const updated = await api.cancelRequirement(id);
      setRequirements((current) => (current ?? []).map((r) => (r.id === id ? updated : r)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusyId(null);
    }
  }

  function updatePoItem(index: number, changes: Partial<PurchaseOrderItemIn>) {
    setPoItems((current) => current.map((item, i) => (i === index ? { ...item, ...changes } : item)));
  }

  async function createPurchaseOrder(event: React.FormEvent) {
    event.preventDefault();
    const validItems = poItems.filter((item) => item.description.trim());
    if (validItems.length === 0) return;
    setSavingPo(true);
    setError(null);
    try {
      const created = await api.createPurchaseOrder({
        project_id: projectId,
        supplier_id: poSupplierId || null,
        expected_delivery_date: poExpectedDate || null,
        items: validItems,
      });
      setPurchaseOrders((current) => [created, ...(current ?? [])]);
      setPoSupplierId("");
      setPoExpectedDate("");
      setPoItems([{ ...EMPTY_PO_ITEM }]);
      setShowPoForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the purchase order.");
    } finally {
      setSavingPo(false);
    }
  }

  async function approvePo(id: string) {
    setBusyId(id);
    setError(null);
    try {
      const updated = await api.approvePurchaseOrder(id);
      setPurchaseOrders((current) => (current ?? []).map((po) => (po.id === id ? updated : po)));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 409
            ? "That action isn't available for this purchase order right now — try refreshing."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setBusyId(null);
    }
  }

  function startOrdering(po: PurchaseOrder) {
    setOrderingId(po.id);
    setOrderSupplierReference("");
    setOrderExpectedDate(po.expected_delivery_date ?? "");
  }

  async function submitOrder(id: string) {
    setBusyId(id);
    setError(null);
    try {
      const updated = await api.orderPurchaseOrder(id, {
        supplier_reference: orderSupplierReference || null,
        expected_delivery_date: orderExpectedDate || null,
      });
      setPurchaseOrders((current) => (current ?? []).map((po) => (po.id === id ? updated : po)));
      setOrderingId(null);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 409
            ? "That action isn't available for this purchase order right now — try refreshing."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setBusyId(null);
    }
  }

  async function cancelPo(id: string) {
    setBusyId(id);
    setError(null);
    try {
      const updated = await api.cancelPurchaseOrder(id);
      setPurchaseOrders((current) => (current ?? []).map((po) => (po.id === id ? updated : po)));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 409
            ? "That action isn't available for this purchase order right now — try refreshing."
            : err.message
          : "Something went wrong."
      );
    } finally {
      setBusyId(null);
    }
  }

  async function downloadPdf(po: PurchaseOrder) {
    setBusyId(po.id);
    setError(null);
    try {
      await api.downloadPurchaseOrderPdf(po.id, po.reference);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download the PDF.");
    } finally {
      setBusyId(null);
    }
  }

  function startReceipt(po: PurchaseOrder) {
    setReceiptForId(po.id);
    setReceiptReference("");
    const remaining: Record<string, number> = {};
    for (const item of po.items) {
      remaining[item.id] = Math.max(item.quantity - item.quantity_received, 0);
    }
    setReceiptQuantities(remaining);
  }

  async function submitReceipt(po: PurchaseOrder) {
    const items: PurchaseReceiptItemIn[] = po.items
      .map((item) => ({
        purchase_order_item_id: item.id,
        quantity_received: receiptQuantities[item.id] ?? 0,
      }))
      .filter((item) => item.quantity_received > 0);
    if (items.length === 0) return;
    setSavingReceipt(true);
    setError(null);
    try {
      await api.recordPurchaseOrderReceipt(po.id, {
        received_at: new Date().toISOString(),
        delivery_reference: receiptReference || null,
        items,
      });
      // The receipt itself flips the PO/item status server-side — re-fetch
      // the PO so this panel shows the real, recomputed status rather than
      // guessing it locally.
      const updated = await api.getPurchaseOrder(po.id);
      setPurchaseOrders((current) => (current ?? []).map((p) => (p.id === po.id ? updated : p)));
      setReceiptForId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not record the delivery.");
    } finally {
      setSavingReceipt(false);
    }
  }

  if (!requirements || !purchaseOrders) {
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
          <CardTitle>Material Requirements</CardTitle>
          {!showRequirementForm && (
            <Button size="sm" onClick={() => setShowRequirementForm(true)}>
              <PlusIcon className="h-4 w-4" />
              Add requirement
            </Button>
          )}
        </CardHeader>
        <CardContent className="pt-4">
          {showRequirementForm && (
            <form onSubmit={createRequirement} className="mb-4 rounded-lg border border-border p-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Description" htmlFor="reqDescription" className="sm:col-span-2">
                  <Input
                    id="reqDescription"
                    required
                    value={requirement.description}
                    onChange={(e) => setRequirement({ ...requirement, description: e.target.value })}
                    placeholder="e.g. 40mm quartz worktop slabs"
                  />
                </Field>
                <Field label="Quantity" htmlFor="reqQuantity">
                  <Input
                    id="reqQuantity"
                    type="number"
                    min="0"
                    step="0.01"
                    value={requirement.required_quantity ?? ""}
                    onChange={(e) =>
                      setRequirement({
                        ...requirement,
                        required_quantity: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  />
                </Field>
                <Field label="Unit" htmlFor="reqUnit">
                  <Input
                    id="reqUnit"
                    value={requirement.unit ?? ""}
                    onChange={(e) => setRequirement({ ...requirement, unit: e.target.value || null })}
                    placeholder="e.g. m2, item, box"
                  />
                </Field>
                <Field label="Required by" htmlFor="reqRequiredBy">
                  <Input
                    id="reqRequiredBy"
                    type="date"
                    value={requirement.required_by_date ?? ""}
                    onChange={(e) =>
                      setRequirement({ ...requirement, required_by_date: e.target.value || null })
                    }
                  />
                </Field>
              </div>
              <div className="mt-4 flex gap-2">
                <Button type="submit" disabled={savingRequirement || !requirement.description.trim()}>
                  {savingRequirement ? "Saving…" : "Save requirement"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setShowRequirementForm(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {requirements.length === 0 ? (
            <EmptyState
              title="No material requirements yet"
              description="Add what this project needs so it can be tracked through to delivery."
              className="py-8"
            />
          ) : (
            <ul className="divide-y divide-border border-t border-border">
              {requirements.map((req) => (
                <li key={req.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{req.description}</p>
                    <p className="text-xs text-muted">
                      {req.required_quantity != null ? `${req.required_quantity} ${req.unit ?? ""}` : ""}
                      {req.required_by_date ? ` · Needed by ${formatDate(req.required_by_date)}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge tone={REQUIREMENT_STATUS_TONE[req.status]}>
                      {REQUIREMENT_STATUS_LABELS[req.status]}
                    </Badge>
                    {req.status !== "cancelled" &&
                      req.status !== "consumed" &&
                      req.status !== "allocated" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busyId === req.id}
                          onClick={() => cancelRequirement(req.id)}
                          aria-label={`Cancel ${req.description}`}
                        >
                          <TrashIcon className="h-4 w-4" />
                        </Button>
                      )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Purchase Orders</CardTitle>
          {!showPoForm && (
            <Button size="sm" onClick={() => setShowPoForm(true)}>
              <PlusIcon className="h-4 w-4" />
              New purchase order
            </Button>
          )}
        </CardHeader>
        <CardContent className="pt-4">
          {showPoForm && (
            <form onSubmit={createPurchaseOrder} className="mb-4 rounded-lg border border-border p-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Supplier" htmlFor="poSupplier">
                  <Select
                    id="poSupplier"
                    value={poSupplierId}
                    onChange={(e) => setPoSupplierId(e.target.value)}
                  >
                    <option value="">No supplier selected</option>
                    {suppliers.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Expected delivery date" htmlFor="poExpectedDate">
                  <Input
                    id="poExpectedDate"
                    type="date"
                    value={poExpectedDate}
                    onChange={(e) => setPoExpectedDate(e.target.value)}
                  />
                </Field>
              </div>

              <p className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-muted">
                Items
              </p>
              <div className="space-y-3">
                {poItems.map((item, index) => (
                  <div key={index} className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                    <Input
                      className="sm:col-span-2"
                      aria-label="Item description"
                      placeholder="Description"
                      value={item.description}
                      onChange={(e) => updatePoItem(index, { description: e.target.value })}
                    />
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      aria-label="Quantity"
                      placeholder="Qty"
                      value={item.quantity}
                      onChange={(e) => updatePoItem(index, { quantity: Number(e.target.value) })}
                    />
                    <Input
                      aria-label="Unit"
                      placeholder="Unit"
                      value={item.unit}
                      onChange={(e) => updatePoItem(index, { unit: e.target.value })}
                    />
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      aria-label="Unit cost"
                      placeholder="Unit cost"
                      value={item.unit_cost}
                      onChange={(e) => updatePoItem(index, { unit_cost: Number(e.target.value) })}
                    />
                  </div>
                ))}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => setPoItems((current) => [...current, { ...EMPTY_PO_ITEM }])}
              >
                <PlusIcon className="h-4 w-4" />
                Add item
              </Button>

              <div className="mt-4 flex gap-2">
                <Button type="submit" disabled={savingPo}>
                  {savingPo ? "Saving…" : "Save draft"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setShowPoForm(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {purchaseOrders.length === 0 ? (
            <EmptyState
              title="No purchase orders yet"
              description="Raise a draft purchase order for this project's materials."
              className="py-8"
            />
          ) : (
            <ul className="divide-y divide-border border-t border-border">
              {purchaseOrders.map((po) => (
                <li key={po.id} className="py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">{po.reference}</p>
                      <p className="text-xs text-muted">
                        {formatCurrencyGBP(po.total)} total
                        {po.expected_delivery_date
                          ? ` · Expected ${formatDate(po.expected_delivery_date)}`
                          : ""}
                        {po.approved_at ? ` · Approved ${formatDateTime(po.approved_at)}` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {po.is_late && <Badge tone="danger">Late</Badge>}
                      <Badge tone={PO_STATUS_TONE[po.status]}>{PO_STATUS_LABELS[po.status]}</Badge>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {po.status === "draft" && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busyId === po.id}
                        onClick={() => approvePo(po.id)}
                      >
                        Approve
                      </Button>
                    )}
                    {po.status === "approved" && orderingId !== po.id && (
                      <Button variant="outline" size="sm" onClick={() => startOrdering(po)}>
                        Mark as ordered
                      </Button>
                    )}
                    {(po.status === "ordered" || po.status === "partially_received") &&
                      receiptForId !== po.id && (
                        <Button variant="outline" size="sm" onClick={() => startReceipt(po)}>
                          Record delivery
                        </Button>
                      )}
                    {po.status !== "cancelled" && po.status !== "received" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busyId === po.id}
                        onClick={() => cancelPo(po.id)}
                        aria-label={`Cancel ${po.reference}`}
                      >
                        <TrashIcon className="h-4 w-4" />
                        Cancel
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busyId === po.id}
                      onClick={() => downloadPdf(po)}
                    >
                      Download PDF
                    </Button>
                  </div>

                  {orderingId === po.id && (
                    <div className="mt-3 grid grid-cols-1 gap-3 rounded-lg border border-border p-3 sm:grid-cols-2">
                      <Field label="Supplier reference" htmlFor={`orderRef-${po.id}`}>
                        <Input
                          id={`orderRef-${po.id}`}
                          value={orderSupplierReference}
                          onChange={(e) => setOrderSupplierReference(e.target.value)}
                          placeholder="Supplier's own order number"
                        />
                      </Field>
                      <Field label="Expected delivery date" htmlFor={`orderDate-${po.id}`}>
                        <Input
                          id={`orderDate-${po.id}`}
                          type="date"
                          value={orderExpectedDate}
                          onChange={(e) => setOrderExpectedDate(e.target.value)}
                        />
                      </Field>
                      <div className="flex gap-2 sm:col-span-2">
                        <Button size="sm" disabled={busyId === po.id} onClick={() => submitOrder(po.id)}>
                          Confirm order
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setOrderingId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}

                  {receiptForId === po.id && (
                    <div className="mt-3 space-y-3 rounded-lg border border-border p-3">
                      {po.items.map((item) => (
                        <div key={item.id} className="grid grid-cols-3 items-end gap-2">
                          <p className="col-span-2 text-sm text-foreground">
                            {item.description}
                            <span className="block text-xs text-muted">
                              {item.quantity_received} of {item.quantity} {item.unit} received
                            </span>
                          </p>
                          <Field label="Receiving now" htmlFor={`receipt-${item.id}`}>
                            <Input
                              id={`receipt-${item.id}`}
                              type="number"
                              min="0"
                              step="0.01"
                              value={receiptQuantities[item.id] ?? 0}
                              onChange={(e) =>
                                setReceiptQuantities((current) => ({
                                  ...current,
                                  [item.id]: Number(e.target.value),
                                }))
                              }
                            />
                          </Field>
                        </div>
                      ))}
                      <Field label="Delivery reference" htmlFor={`deliveryRef-${po.id}`}>
                        <Input
                          id={`deliveryRef-${po.id}`}
                          value={receiptReference}
                          onChange={(e) => setReceiptReference(e.target.value)}
                          placeholder="Delivery note number"
                        />
                      </Field>
                      <div className="flex gap-2">
                        <Button size="sm" disabled={savingReceipt} onClick={() => submitReceipt(po)}>
                          {savingReceipt ? "Saving…" : "Save delivery"}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setReceiptForId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
