"use client";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { readConsent, writeConsent, type Consent } from "@/lib/consent";
import { api, type MarketingPreference } from "@/lib/api";

const defaults = { preferences: false, analytics: false, marketing: false };
export function PrivacyCard() {
  const [value, setValue] = useState<Consent | null>(() => readConsent());
  const [marketingEmail, setMarketingEmail] = useState<MarketingPreference | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailSaving, setEmailSaving] = useState(false);
  useEffect(() => {
    let active = true;
    api.getMarketingPreference()
      .then((preference) => { if (active) setMarketingEmail(preference); })
      .catch(() => { if (active) setEmailError("Could not load your marketing email preference."); });
    return () => { active = false; };
  }, []);
  const current = value ?? { essential: true, ...defaults };
  function change(key: keyof typeof defaults, checked: boolean) { setValue(writeConsent({ preferences: current.preferences, analytics: current.analytics, marketing: current.marketing, [key]: checked })); }
  async function changeMarketingEmail(enabled: boolean) {
    setEmailSaving(true);
    setEmailError(null);
    try {
      setMarketingEmail(await api.setMarketingPreference(enabled));
    } catch {
      setEmailError("Could not update your marketing email preference. Please try again.");
    } finally {
      setEmailSaving(false);
    }
  }
  return <Card><CardHeader><CardTitle>Privacy &amp; communications</CardTitle></CardHeader><CardContent className="space-y-4 text-sm"><p className="text-muted">Essential storage supports sign-in, security and necessary service operation and cannot be disabled. Optional categories are off unless you enable them.</p><label className="flex gap-2"><input checked disabled type="checkbox" /> Essential</label>{(["preferences", "analytics", "marketing"] as const).map((key) => <label className="flex gap-2" key={key}><input checked={current[key]} onChange={(e) => change(key, e.target.checked)} type="checkbox" /> {key[0].toUpperCase() + key.slice(1)}</label>)}<Button type="button" onClick={() => setValue(writeConsent({ preferences: current.preferences, analytics: current.analytics, marketing: current.marketing }))}>Save browser preferences</Button><div className="border-t border-border pt-4"><p className="font-medium">Marketing email</p><p className="mt-1 text-xs text-muted">Choose whether GeoCore may send optional product, quote follow-up, and review-request emails. This does not affect verification, password/security, billing, invitations, or necessary service messages.</p><label className="mt-3 flex gap-2"><input checked={marketingEmail?.enabled ?? false} disabled={marketingEmail === null || emailSaving} onChange={(e) => void changeMarketingEmail(e.target.checked)} type="checkbox" /> Receive marketing email</label>{emailError && <p className="mt-2 text-xs text-danger">{emailError}</p>}</div></CardContent></Card>;
}
