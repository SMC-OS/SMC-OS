/**
 * /start campaign landing — UTM capture, signup-link wiring and event
 * tracking. Dependency-free and SSR-safe: every export no-ops on the server.
 *
 * UTM parameters arriving on the landing URL are persisted to
 * sessionStorage (this tab) and localStorage (return visits), and appended
 * to every "Start free" CTA so the signup flow on the app host can
 * attribute the conversion. Nothing sensitive ever goes into a URL — only
 * the five standard, non-PII campaign parameters.
 */

export const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
] as const;

export type UtmKey = (typeof UTM_KEYS)[number];
export type UtmParams = Partial<Record<UtmKey, string>>;

const STORAGE_KEY = "geocore_start_utm";

declare global {
  interface Window {
    dataLayer?: Record<string, unknown>[];
    fbq?: (...args: unknown[]) => void;
  }
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}

/** Read UTM params from the current URL. */
function readUrlUtm(): UtmParams {
  if (!isBrowser()) return {};
  const search = new URLSearchParams(window.location.search);
  const found: UtmParams = {};
  for (const key of UTM_KEYS) {
    const value = search.get(key);
    if (value) found[key] = value.slice(0, 200);
  }
  return found;
}

/** Persisted params: URL wins over storage, session wins over local. */
export function captureUtmParams(): UtmParams {
  if (!isBrowser()) return {};
  const fromUrl = readUrlUtm();
  let stored: UtmParams = {};
  try {
    stored = {
      ...JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}"),
      ...JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "{}"),
    };
  } catch {
    stored = {};
  }
  const merged = { ...stored, ...fromUrl };
  try {
    const serialised = JSON.stringify(merged);
    window.sessionStorage.setItem(STORAGE_KEY, serialised);
    window.localStorage.setItem(STORAGE_KEY, serialised);
  } catch {
    // Storage unavailable (private mode etc.) — tracking still works.
  }
  return merged;
}

export function getStoredUtm(): UtmParams {
  if (!isBrowser()) return {};
  try {
    return {
      ...JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}"),
      ...JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) ?? "{}"),
    };
  } catch {
    return {};
  }
}

/** Signup URL on the app host with persisted UTM params appended. */
export function signupUrl(base: string): string {
  const utm = getStoredUtm();
  const params = new URLSearchParams();
  for (const key of UTM_KEYS) {
    const value = utm[key];
    if (value) params.set(key, value);
  }
  const query = params.toString();
  if (!query) return base;
  // The base may already carry a query (e.g. ?plan=pro from a pricing
  // CTA) — append with the right separator rather than a second "?".
  return `${base}${base.includes("?") ? "&" : "?"}${query}`;
}

// Meta Pixel is OFF by default: it loads only when NEXT_PUBLIC_META_PIXEL_ID
// is explicitly set at build time (an ID is never committed to the repo).
// The repo has no cookie/marketing consent system (verified Sprint Phase B
// audit — no CMP, banner or consent store anywhere), so there is no consent
// signal to gate on; the env-var gate is the whole control. When a consent
// system lands, gate ensureMetaPixel() on marketing consent here. No CAPI.
const META_PIXEL_ID = process.env.NEXT_PUBLIC_META_PIXEL_ID;
let pixelLoaded = false;

/** Load the Meta Pixel (fbevents) only when an ID is configured. */
function ensureMetaPixel(): void {
  if (!isBrowser() || !META_PIXEL_ID || pixelLoaded) return;
  pixelLoaded = true;

  const w = window as Window & { _fbq?: Window["fbq"] };
  if (!w.fbq) {
    const fbq = function (...args: unknown[]) {
      (fbq.queue as unknown[]).push(args);
    } as Window["fbq"] & { queue: unknown[]; loaded?: boolean; version?: string };
    fbq.queue = [];
    fbq.loaded = true;
    fbq.version = "2.0";
    w.fbq = fbq;
    w._fbq = fbq;

    const script = document.createElement("script");
    script.async = true;
    script.src = "https://connect.facebook.net/en_US/fbevents.js";
    document.head.appendChild(script);
  }
  w.fbq?.("init", META_PIXEL_ID);
  w.fbq?.("track", "PageView");
}

/** Push an event to the dataLayer and, when configured, the Meta Pixel. */
export function track(event: string, props: Record<string, unknown> = {}): void {
  if (!isBrowser()) return;
  window.dataLayer = window.dataLayer ?? [];
  window.dataLayer.push({ event, page: "/start", ...props });
  if (META_PIXEL_ID) {
    ensureMetaPixel();
    window.fbq?.("trackCustom", event, props);
  }
}

let initialised = false;

/** Mount-once initialisation: capture UTMs, load pixel, fire page view. */
export function initStartTracking(): void {
  if (!isBrowser() || initialised) return;
  initialised = true;
  const utm = captureUtmParams();
  if (META_PIXEL_ID) ensureMetaPixel();
  track("campaign_landing_view", {
    ...utm,
    has_utm: Object.keys(utm).length > 0,
  });
}
