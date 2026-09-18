"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { AlertTriangleIcon, PlusIcon, TrashIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP, formatDate } from "@/lib/utils";
import {
  COST_CATEGORIES,
  COST_CATEGORY_LABELS,
  COST_STATES,
  COST_STATE_LABELS,
  type CostCategory,
  type CostState,
} from "@/types/financials";
import type { ProjectCostEntry, ProjectFinancialSummary } from "@/types/financials";

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

const EMPTY_FORM = {
  description: "",
  category: "material" as CostCategory,
  state: "budgeted" as CostState,
  total_cost: "",
  supplier_or_payee: "",
  reference: "",
  cost_date: "",
};

/**
 * GeoCore Premium OS Plan 04 (Sprint 043), Task 12-14 — a project's
 * commercial control layer: Base Contract / Approved Variations / Current
 * Contract, cost ledger by state, and forecast/actual profitability.
 *
 * Every headline figure is either a real derived number or explicitly
 * null/"Unknown" — never a fabricated placeholder (Task 12's core rule).
 * cost_data_status is always shown alongside any forecast profit/margin
 * so a partial-data figure is never mistaken for a confident one.
 */
export function ProjectFinancialsPanel({ projectId }: { projectId: string }) {
  const [summary, setSummary] = useState<ProjectFinancialSummary | null>(null);
  const [costs, setCosts] = useState<ProjectCostEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function load() {
    api
      .getProjectFinancialSummary(projectId)
      .then(setSummary)
      .catch(() => setError("Could not load the financial summary."));
    api
      .getProjectCosts(projectId)
      .then(setCosts)
      .catch(() => setError("Could not load the cost ledger."));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function addCost(event: React.FormEvent) {
    event.preventDefault();
    const totalCost = Number(form.total_cost);
    if (!form.description.trim() || Number.isNaN(totalCost) || totalCost < 0) return;

    setSaving(true);
    setError(null);
    try {
      const created = await api.createProjectCost(projectId, {
        description: form.description.trim(),
        category: form.category,
        state: form.state,
        total_cost: totalCost,
        supplier_or_payee: form.supplier_or_payee.trim() || null,
        reference: form.reference.trim() || null,
        cost_date: form.cost_date || null,
      });
      setCosts((current) => [...(current ?? []), created]);
      setForm(EMPTY_FORM);
      setShowForm(false);
      // Every headline figure below depends on the full cost set, so the
      // summary is re-fetched from the server rather than recomputed
      // client-side — the aggregation and cost_data_status rules are the
      // backend's alone to apply.
      api.getProjectFinancialSummary(projectId).then(setSummary).catch(() => {});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the cost.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCost(costEntryId: string) {
    setDeletingId(costEntryId);
    setError(null);
    try {
      await api.deleteProjectCost(projectId, costEntryId);
      setCosts((current) => (current ?? []).filter((entry) => entry.id !== costEntryId));
      api.getProjectFinancialSummary(projectId).then(setSummary).catch(() => {});
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the cost.");
    } finally {
      setDeletingId(null);
    }
  }

  if (!summary || !costs) {
    return (
      <div>
        {error && <p className="mb-3 text-sm text-danger">{error}</p>}
        {!error && <p className="text-sm text-muted">Loading…</p>}
      </div>
    );
  }

  const { contract, costs: costSummary, profitability } = summary;

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Contract Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <SummaryRow
              label="Base contract"
              value={
                contract.base_contract_value !== null
                  ? formatCurrencyGBP(contract.base_contract_value)
                  : "Unknown — no approved quote linked"
              }
            />
            <SummaryRow
              label="Approved variations"
              value={formatCurrencyGBP(contract.approved_variations_total)}
            />
            <div className="mt-2 border-t border-border pt-2">
              <SummaryRow
                label="Current contract value"
                value={
                  contract.current_contract_value !== null
                    ? formatCurrencyGBP(contract.current_contract_value)
                    : "Unknown"
                }
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Cost Summary</CardTitle>
            <Badge tone={costSummary.cost_data_status === "complete" ? "success" : "neutral"}>
              {costSummary.cost_data_status === "none"
                ? "No costs recorded"
                : costSummary.cost_data_status === "partial"
                  ? "Partial cost data"
                  : "Complete"}
            </Badge>
          </CardHeader>
          <CardContent>
            <SummaryRow label="Budgeted" value={formatCurrencyGBP(costSummary.budgeted_cost)} />
            <SummaryRow label="Committed" value={formatCurrencyGBP(costSummary.committed_cost)} />
            <SummaryRow label="Actual" value={formatCurrencyGBP(costSummary.actual_cost)} />
            <div className="mt-2 border-t border-border pt-2">
              <SummaryRow label="Forecast cost" value={formatCurrencyGBP(costSummary.forecast_cost)} />
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Profitability</CardTitle>
            {profitability.margin_risk && (
              <Badge tone="danger">
                <AlertTriangleIcon className="mr-1 h-3 w-3" />
                Margin risk
              </Badge>
            )}
          </CardHeader>
          <CardContent>
            {costSummary.cost_data_status !== "complete" && (
              <p className="mb-3 text-xs text-muted">
                Forecast based on recorded costs — cost data for this project is{" "}
                {costSummary.cost_data_status === "none" ? "not yet recorded" : "incomplete"}, so
                figures below may move as more costs are added.
              </p>
            )}
            <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  Forecast
                </p>
                <SummaryRow
                  label="Gross profit"
                  value={
                    profitability.forecast_gross_profit !== null
                      ? formatCurrencyGBP(profitability.forecast_gross_profit)
                      : "Unknown"
                  }
                />
                <SummaryRow
                  label="Gross margin"
                  value={
                    profitability.forecast_gross_margin_percent !== null
                      ? `${profitability.forecast_gross_margin_percent.toFixed(1)}%`
                      : "Unknown"
                  }
                />
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  Actual
                </p>
                <SummaryRow
                  label="Gross profit"
                  value={
                    profitability.actual_gross_profit !== null
                      ? formatCurrencyGBP(profitability.actual_gross_profit)
                      : "Unknown"
                  }
                />
                <SummaryRow
                  label="Gross margin"
                  value={
                    profitability.actual_gross_margin_percent !== null
                      ? `${profitability.actual_gross_margin_percent.toFixed(1)}%`
                      : "Unknown"
                  }
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Cost Breakdown</CardTitle>
          {!showForm && (
            <Button size="sm" onClick={() => setShowForm(true)}>
              <PlusIcon className="h-4 w-4" />
              Add cost
            </Button>
          )}
        </CardHeader>
        <CardContent className="pt-4">
          {showForm && (
            <form
              onSubmit={addCost}
              className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-border p-4 sm:grid-cols-2"
            >
              <Field label="Description" htmlFor="costDescription" className="sm:col-span-2">
                <Input
                  id="costDescription"
                  required
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="e.g. Quartz slab — Calacatta"
                />
              </Field>
              <Field label="Category" htmlFor="costCategory">
                <Select
                  id="costCategory"
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value as CostCategory })}
                >
                  {COST_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {COST_CATEGORY_LABELS[category]}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="State" htmlFor="costState">
                <Select
                  id="costState"
                  value={form.state}
                  onChange={(e) => setForm({ ...form, state: e.target.value as CostState })}
                >
                  {COST_STATES.map((state) => (
                    <option key={state} value={state}>
                      {COST_STATE_LABELS[state]}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Total cost" htmlFor="costTotal">
                <Input
                  id="costTotal"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={form.total_cost}
                  onChange={(e) => setForm({ ...form, total_cost: e.target.value })}
                />
              </Field>
              <Field label="Cost date" htmlFor="costDate">
                <Input
                  id="costDate"
                  type="date"
                  value={form.cost_date}
                  onChange={(e) => setForm({ ...form, cost_date: e.target.value })}
                />
              </Field>
              <Field label="Supplier / payee" htmlFor="costSupplier">
                <Input
                  id="costSupplier"
                  value={form.supplier_or_payee}
                  onChange={(e) => setForm({ ...form, supplier_or_payee: e.target.value })}
                />
              </Field>
              <Field label="Reference" htmlFor="costReference">
                <Input
                  id="costReference"
                  value={form.reference}
                  onChange={(e) => setForm({ ...form, reference: e.target.value })}
                />
              </Field>
              <div className="flex gap-2 sm:col-span-2">
                <Button type="submit" disabled={saving || !form.description.trim()}>
                  {saving ? "Saving…" : "Save cost"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {costs.length === 0 ? (
            <EmptyState
              title="No costs recorded yet"
              description="Add budgeted, committed or actual costs as they're known."
              className="py-8"
            />
          ) : (
            <ul className="divide-y divide-border border-t border-border">
              {costs.map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground">{entry.description}</p>
                    <p className="text-xs text-muted">
                      {COST_CATEGORY_LABELS[entry.category]} &middot;{" "}
                      {COST_STATE_LABELS[entry.state]}
                      {entry.supplier_or_payee ? ` · ${entry.supplier_or_payee}` : ""}
                      {entry.cost_date ? ` · ${formatDate(entry.cost_date)}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="text-sm font-medium text-foreground">
                      {formatCurrencyGBP(entry.total_cost)}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={deletingId === entry.id}
                      onClick={() => deleteCost(entry.id)}
                      aria-label={`Delete cost "${entry.description}"`}
                    >
                      <TrashIcon className="h-4 w-4" />
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
