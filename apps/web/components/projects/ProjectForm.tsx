"use client";

import { useEffect, useState } from "react";

import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { currencySymbol } from "@/lib/utils";
import type { Customer } from "@/types/customer";
import type { ProjectCreate } from "@/types/project";
import type { Trade } from "@/types/quote";

/**
 * The project form — Sprint 036, Workstream F.
 *
 * Shared by "New project" and the edit panel on the detail page. A
 * project record is now the job: where it is, what kind of work, when it
 * starts, when it is due, what it is worth — everything a person needs to
 * schedule and price it, none of which had anywhere to live before.
 *
 * `project_type` uses the same vocabulary as a quote's trade
 * (GET /quotes/meta/trades), so a project created from an approved quote
 * and one created by hand describe themselves the same way.
 */
export function ProjectForm({
  initial,
  submitLabel,
  initialCustomerId,
  onSubmit,
}: {
  initial?: Partial<ProjectCreate>;
  submitLabel: string;
  initialCustomerId?: string;
  onSubmit: (values: ProjectCreate) => Promise<void>;
}) {
  const { currency } = useWorkspace();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);

  const [name, setName] = useState(initial?.name ?? "");
  const [customerId, setCustomerId] = useState(
    initial?.customer_id ?? initialCustomerId ?? ""
  );
  const [projectType, setProjectType] = useState(initial?.project_type ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [addressLine1, setAddressLine1] = useState(initial?.site_address_line1 ?? "");
  const [addressLine2, setAddressLine2] = useState(initial?.site_address_line2 ?? "");
  const [city, setCity] = useState(initial?.site_city ?? "");
  const [postcode, setPostcode] = useState(initial?.site_postcode ?? "");
  const [startDate, setStartDate] = useState(initial?.start_date ?? "");
  const [targetDate, setTargetDate] = useState(initial?.target_completion_date ?? "");
  const [value, setValue] = useState(
    initial?.estimated_value != null ? String(initial.estimated_value) : ""
  );
  const [notes, setNotes] = useState(initial?.notes ?? "");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getCustomers(200).then(setCustomers).catch(() => {});
    api.getTrades().then(setTrades).catch(() => {});
  }, []);

  function selectCustomer(id: string) {
    setCustomerId(id);
    const selected = customers.find((customer) => customer.id === id);
    if (!selected) return;
    // Same prefill reasoning as the quote builder: the customer's address
    // is usually the site, and anyone who needs a different one types
    // over it. Only prefills when the site address is still empty, so it
    // never overwrites something already entered.
    if (!addressLine1 && !city && !postcode) {
      setAddressLine1(selected.address_line1 ?? "");
      setAddressLine2(selected.address_line2 ?? "");
      setCity(selected.city ?? "");
      setPostcode(selected.postcode ?? "");
    }
  }

  // A target completion date before the start date is a data-entry
  // mistake, caught here where it can be explained rather than accepted
  // and rendered as a job that finishes before it begins.
  const dateOrderError =
    startDate && targetDate && targetDate < startDate
      ? "The target completion date is before the start date."
      : null;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (dateOrderError) return;

    setSubmitting(true);
    setError(null);

    try {
      await onSubmit({
        name: name.trim(),
        customer_id: customerId || null,
        project_type: projectType || null,
        description: description.trim() || null,
        site_address_line1: addressLine1.trim() || null,
        site_address_line2: addressLine2.trim() || null,
        site_city: city.trim() || null,
        site_postcode: postcode.trim() || null,
        start_date: startDate || null,
        target_completion_date: targetDate || null,
        estimated_value: value ? Number(value) : null,
        notes: notes.trim() || null,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <Field label="Project name" htmlFor="name" required>
            <Input
              id="name"
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Riverside kitchen renovation"
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

            <Field label="Type of work" htmlFor="projectType">
              <Select
                id="projectType"
                value={projectType ?? ""}
                onChange={(e) => setProjectType(e.target.value)}
              >
                <option value="">— Not specified —</option>
                {trades.map((trade) => (
                  <option key={trade.key} value={trade.key}>
                    {trade.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Description" htmlFor="description">
            <Textarea
              id="description"
              rows={3}
              value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What the job involves."
            />
          </Field>

          <div className="border-t border-border pt-5">
            <p className="mb-3 text-sm font-medium text-foreground">Site address</p>
            <div className="flex flex-col gap-5">
              <Field label="Address line 1" htmlFor="siteAddress1">
                <Input
                  id="siteAddress1"
                  value={addressLine1 ?? ""}
                  onChange={(e) => setAddressLine1(e.target.value)}
                />
              </Field>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field label="Town or city" htmlFor="siteCity">
                  <Input
                    id="siteCity"
                    value={city ?? ""}
                    onChange={(e) => setCity(e.target.value)}
                  />
                </Field>
                <Field label="Postcode" htmlFor="sitePostcode">
                  <Input
                    id="sitePostcode"
                    value={postcode ?? ""}
                    onChange={(e) => setPostcode(e.target.value)}
                    className="uppercase"
                  />
                </Field>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-5 border-t border-border pt-5 sm:grid-cols-3">
            <Field
              label="Start date"
              htmlFor="startDate"
              hint="Shows on the calendar."
            >
              <Input
                id="startDate"
                type="date"
                value={startDate ?? ""}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </Field>
            <Field
              label="Target completion"
              htmlFor="targetDate"
              error={dateOrderError ?? undefined}
            >
              <Input
                id="targetDate"
                type="date"
                value={targetDate ?? ""}
                onChange={(e) => setTargetDate(e.target.value)}
                aria-invalid={dateOrderError ? true : undefined}
                aria-describedby={dateOrderError ? "targetDate-error" : undefined}
              />
            </Field>
            <Field label={`Value (${currencySymbol(currency)})`} htmlFor="value">
              <Input
                id="value"
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="0.00"
              />
            </Field>
          </div>

          <Field label="Notes" htmlFor="notes">
            <Textarea
              id="notes"
              rows={2}
              value={notes ?? ""}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>

          {error && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <Button
            type="submit"
            size="lg"
            disabled={submitting || Boolean(dateOrderError)}
            className="self-start"
          >
            {submitting ? "Saving…" : submitLabel}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
