export const CONSENT_VERSION = "2026-09-28";
export const CONSENT_STORAGE_KEY = "geocore_consent";

export type ConsentPreferences = { essential: true; preferences: boolean; analytics: boolean; marketing: boolean };
export type ConsentRecord = ConsentPreferences & { version: string; source: "banner" | "preferences"; timestamp: string };

const defaults: ConsentPreferences = { essential: true, preferences: false, analytics: false, marketing: false };
function browser() { return typeof window !== "undefined"; }

export function readConsent(): ConsentRecord | null {
  if (!browser()) return null;
  try {
    const value = JSON.parse(window.localStorage.getItem(CONSENT_STORAGE_KEY) ?? "null") as ConsentRecord | null;
    return value?.version === CONSENT_VERSION && value.essential === true ? value : null;
  } catch { return null; }
}
export function preferences(): ConsentPreferences { return readConsent() ?? defaults; }
export function hasConsent(category: keyof ConsentPreferences): boolean { return category === "essential" || preferences()[category]; }
export function saveConsent(next: Omit<ConsentPreferences, "essential">, source: ConsentRecord["source"]): ConsentRecord {
  const record: ConsentRecord = { essential: true, ...next, version: CONSENT_VERSION, source, timestamp: new Date().toISOString() };
  window.localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(record));
  window.dispatchEvent(new Event("geocore:consent-changed"));
  return record;
}
