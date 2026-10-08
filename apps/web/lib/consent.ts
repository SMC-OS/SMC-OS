export const CONSENT_KEY = "geocore_consent";
export const CONSENT_VERSION = "2026-09-28";
export type Consent = { essential: true; preferences: boolean; analytics: boolean; marketing: boolean; version: string; source: "preferences"; timestamp: string };
export function readConsent(): Consent | null { try { const v = JSON.parse(localStorage.getItem(CONSENT_KEY) ?? "null"); return v?.version === CONSENT_VERSION ? v : null; } catch { return null; } }
export function writeConsent(value: Omit<Consent, "essential" | "version" | "source" | "timestamp">): Consent { const next: Consent = { essential: true, ...value, version: CONSENT_VERSION, source: "preferences", timestamp: new Date().toISOString() }; localStorage.setItem(CONSENT_KEY, JSON.stringify(next)); window.dispatchEvent(new Event("geocore:consent-changed")); return next; }
