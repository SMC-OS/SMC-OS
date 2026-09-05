"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { SUPPORTED_CURRENCIES } from "@/types/tenant";
import type { TenantProfile, TenantProfileUpdate } from "@/types/tenant";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";

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
];

// Sprint 036 (Workstream I) — `logo_url` and `document_footer` moved to
// the Branding section. They are how documents *look*, not who the
// company legally is, and stacking them under the statutory details is
// part of what made the old single Settings page a 483-line scroll.

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
  const [currency, setCurrency] = useState("GBP");
  const { refresh: refreshWorkspace } = useWorkspace();

  useEffect(() => {
    api
      .getCompanyProfile()
      .then((loaded) => {
        setProfile(loaded);
        setForm(toForm(loaded));
        setCurrency(loaded.currency ?? "GBP");
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

    if (currency !== (profile.currency ?? "GBP")) {
      changed.currency = currency;
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
      setCurrency(updated.currency ?? "GBP");
      // The currency drives every money format in the app, so the shared
      // workspace context has to hear about a change here.
      refreshWorkspace();
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

            {/* Sprint 036 — the workspace currency. A select rather than
                a text field: the backend accepts only currencies GeoCore
                can actually render on screen and on a PDF, and a free
                text box would invite a code that produces documents with
                bare numbers on them. */}
            <Field
              label="Currency"
              htmlFor="company-currency"
              hint="Used across the app and on new quotes. Existing quotes keep the currency they were created in."
            >
              <Select
                id="company-currency"
                value={currency}
                onChange={(e) => {
                  setCurrency(e.target.value);
                  setSaved(false);
                }}
              >
                {SUPPORTED_CURRENCIES.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </Select>
            </Field>

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
