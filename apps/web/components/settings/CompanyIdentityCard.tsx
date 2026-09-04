"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import type { TenantProfile, TenantProfileUpdate } from "@/types/tenant";

// Sprint 034 — the business identity this tenant's own customers see on
// quotes and invoices. Deliberately not the platform's brand: the product
// a tenant subscribes to is not the company their customer is buying from,
// so nothing on this screen is prefilled with a platform name.
const FIELDS: { key: keyof TenantProfileUpdate; label: string; hint?: string; wide?: boolean }[] = [
  { key: "name", label: "Workspace name", hint: "Shown to your team inside the product." },
  {
    key: "legal_name",
    label: "Registered company name",
    hint: "The legal entity, exactly as registered at Companies House.",
  },
  {
    key: "trading_name",
    label: "Trading name",
    hint: "Leave blank if you trade under the registered name.",
  },
  { key: "address_line1", label: "Address line 1" },
  { key: "address_line2", label: "Address line 2" },
  { key: "city", label: "Town / city" },
  { key: "postcode", label: "Postcode" },
  { key: "country", label: "Country" },
  { key: "contact_phone", label: "Business phone" },
  { key: "contact_email", label: "Business email" },
  { key: "website", label: "Website" },
  { key: "company_number", label: "Company registration number" },
  {
    key: "vat_number",
    label: "VAT registration number",
    hint: "Leave blank if you are not VAT registered — it is omitted rather than guessed.",
  },
  { key: "logo_url", label: "Logo URL", wide: true },
  {
    key: "document_footer",
    label: "Document footer",
    hint: "Appears at the bottom of every quote and invoice — payment terms, registered office, etc.",
    wide: true,
  },
];

type FormState = Record<string, string>;

function toForm(profile: TenantProfile): FormState {
  return Object.fromEntries(
    FIELDS.map(({ key }) => [key, (profile[key as keyof TenantProfile] as string | null) ?? ""])
  );
}

export default function CompanyIdentityCard() {
  const [profile, setProfile] = useState<TenantProfile | null>(null);
  const [form, setForm] = useState<FormState>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api
      .getCompanyProfile()
      .then((loaded) => {
        setProfile(loaded);
        setForm(toForm(loaded));
      })
      .catch(() => setLoadError("Could not load your company details."));
  }, []);

  function update(key: string, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;

    setSaving(true);
    setSaveError(null);
    setSaved(false);

    // Send only what actually changed. The API applies PATCH semantics, so
    // an untouched field is never written — and never blanked — by a save.
    const changed: TenantProfileUpdate = {};
    for (const { key } of FIELDS) {
      const next = form[key] ?? "";
      const previous = (profile[key as keyof TenantProfile] as string | null) ?? "";
      if (next !== previous) {
        (changed as Record<string, string>)[key] = next;
      }
    }

    if (Object.keys(changed).length === 0) {
      setSaving(false);
      setSaved(true);
      return;
    }

    try {
      const updated = await api.updateCompanyProfile(changed);
      setProfile(updated);
      setForm(toForm(updated));
      setSaved(true);
    } catch (err) {
      setSaveError(
        err instanceof ApiError && err.status === 403
          ? "Only workspace owners can change company details."
          : "Something went wrong."
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Company identity</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-muted">
          These details appear on the quotes and invoices your customers
          receive. They are yours alone — no other workspace sees or shares
          them.
        </p>

        {loadError && <p className="text-sm text-danger">{loadError}</p>}

        {!profile && !loadError && (
          <p className="text-center text-sm text-muted">Loading…</p>
        )}

        {profile && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              {FIELDS.map(({ key, label, hint, wide }) => (
                <Field
                  key={key}
                  label={label}
                  htmlFor={`company-${key}`}
                  className={wide ? "sm:col-span-2" : undefined}
                >
                  <Input
                    id={`company-${key}`}
                    value={form[key] ?? ""}
                    onChange={(e) => update(key, e.target.value)}
                  />
                  {hint && <span className="text-xs text-muted">{hint}</span>}
                </Field>
              ))}
            </div>

            {saveError && <p className="text-sm text-danger">{saveError}</p>}
            {saved && !saveError && (
              <p className="text-sm text-success">Company details saved.</p>
            )}

            <div>
              <Button type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save company details"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
