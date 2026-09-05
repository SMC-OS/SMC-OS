"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { ChoiceChip, Field, Input, Textarea } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";
import { CUSTOMER_TYPES, CUSTOMER_TYPE_LABELS, type CustomerCreate, type CustomerType } from "@/types/customer";

/**
 * The customer form — Sprint 036, Workstream D.
 *
 * Shared by "New customer" and the edit panel on the detail page, so the
 * two cannot drift into asking for different things.
 *
 * `name` stays the only required field even for a company customer: it is
 * the person you actually deal with, and a commercial job with a company
 * name but no contact is a job nobody can ring. `company_name` appears
 * only when "Company" is selected — showing it for an individual is a
 * field to skip on every single record.
 */
export function CustomerForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: Partial<CustomerCreate>;
  submitLabel: string;
  onSubmit: (values: CustomerCreate) => Promise<void>;
}) {
  const [customerType, setCustomerType] = useState<CustomerType>(
    (initial?.customer_type as CustomerType) ?? "individual"
  );
  const [name, setName] = useState(initial?.name ?? "");
  const [companyName, setCompanyName] = useState(initial?.company_name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [addressLine1, setAddressLine1] = useState(initial?.address_line1 ?? "");
  const [addressLine2, setAddressLine2] = useState(initial?.address_line2 ?? "");
  const [city, setCity] = useState(initial?.city ?? "");
  const [postcode, setPostcode] = useState(initial?.postcode ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await onSubmit({
        name: name.trim(),
        customer_type: customerType,
        // Empty strings are sent as null so a cleared field genuinely
        // clears rather than storing "".
        company_name: customerType === "company" ? companyName.trim() || null : null,
        email: email.trim() || null,
        phone: phone.trim() || null,
        address_line1: addressLine1.trim() || null,
        address_line2: addressLine2.trim() || null,
        city: city.trim() || null,
        postcode: postcode.trim() || null,
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
          <fieldset className="min-w-0">
            <legend className="mb-2 text-sm font-medium text-foreground">
              Customer type
            </legend>
            <div className="grid grid-cols-2 gap-2">
              {CUSTOMER_TYPES.map((type) => (
                <ChoiceChip
                  key={type}
                  name="customer_type"
                  value={type}
                  checked={customerType === type}
                  onChange={(value) => setCustomerType(value as CustomerType)}
                >
                  {CUSTOMER_TYPE_LABELS[type]}
                </ChoiceChip>
              ))}
            </div>
          </fieldset>

          {customerType === "company" && (
            <Field label="Company name" htmlFor="companyName">
              <Input
                id="companyName"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="e.g. Okafor Developments Ltd"
              />
            </Field>
          )}

          <Field
            label={customerType === "company" ? "Main contact" : "Full name"}
            htmlFor="name"
            required
            hint={
              customerType === "company"
                ? "The person you actually deal with at this company."
                : undefined
            }
          >
            <Input
              id="name"
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. James Okafor"
            />
          </Field>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <Field label="Email" htmlFor="email">
              <Input
                id="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="james@example.com"
              />
            </Field>
            <Field label="Phone" htmlFor="phone">
              <Input
                id="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="07123 456789"
              />
            </Field>
          </div>

          <div className="border-t border-border pt-5">
            <p className="mb-3 text-sm font-medium text-foreground">Address</p>
            <div className="flex flex-col gap-5">
              <Field label="Address line 1" htmlFor="addressLine1">
                <Input
                  id="addressLine1"
                  value={addressLine1}
                  onChange={(e) => setAddressLine1(e.target.value)}
                  placeholder="14 Elm Road"
                />
              </Field>
              <Field label="Address line 2" htmlFor="addressLine2">
                <Input
                  id="addressLine2"
                  value={addressLine2}
                  onChange={(e) => setAddressLine2(e.target.value)}
                />
              </Field>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field label="Town or city" htmlFor="city">
                  <Input
                    id="city"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="Manchester"
                  />
                </Field>
                <Field label="Postcode" htmlFor="postcode">
                  <Input
                    id="postcode"
                    value={postcode}
                    onChange={(e) => setPostcode(e.target.value)}
                    placeholder="M1 4BT"
                    // Uppercase because a UK postcode is conventionally
                    // written that way, applied by CSS so the value the
                    // user typed is what they see.
                    className="uppercase"
                  />
                </Field>
              </div>
            </div>
          </div>

          <Field
            label="Notes"
            htmlFor="notes"
            hint="Access arrangements, who to ask for, payment terms — anything worth remembering."
          >
            <Textarea
              id="notes"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>

          {error && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" size="lg" disabled={submitting} className="self-start">
            {submitting ? "Saving…" : submitLabel}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
