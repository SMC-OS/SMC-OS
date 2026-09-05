/**
 * Minimal classnames joiner. Deliberately dependency-free (no clsx/tailwind-merge)
 * to avoid adding new packages for something this small.
 */
export function cn(
  ...classes: Array<string | false | null | undefined>
): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Sprint 036 (Workstream C) — money formatting takes the currency it is
 * formatting rather than assuming one.
 *
 * Every workspace on GeoCore today is a UK business, so GBP remains the
 * default and nothing about the current product changes. What changes is
 * that the assumption now lives in one defaulted parameter instead of
 * being spelled out at forty call sites, so a workspace configured for
 * EUR renders euros everywhere rather than pounds with the wrong symbol.
 *
 * `maximumFractionDigits: 0` is kept for the compact display used on
 * dashboard tiles; `formatMoney` below is the exact variant for anywhere
 * pence matter — a quote line, a total, an invoice.
 */
export function formatCurrency(value: number, currency = "GBP"): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

/** Exact money — two decimal places. Use anywhere a figure is a price
 * someone will check, rather than a headline. */
export function formatMoney(value: number, currency = "GBP"): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * The currency symbol alone, for prefixing an input.
 *
 * Derived from Intl rather than a hand-kept map, so it stays correct for
 * any currency the backend accepts. The fallback is the code itself,
 * which is honest — better than showing a pound sign next to euros.
 */
export function currencySymbol(currency = "GBP"): string {
  try {
    const parts = new Intl.NumberFormat("en-GB", {
      style: "currency",
      currency,
    }).formatToParts(0);
    return parts.find((part) => part.type === "currency")?.value ?? currency;
  } catch {
    return currency;
  }
}

/**
 * Retained so no existing call site breaks. New code should call
 * formatCurrency(value, currency) with the workspace's own currency.
 */
export function formatCurrencyGBP(value: number): string {
  return formatCurrency(value, "GBP");
}

/** A calendar date, for anything stored as a DATE rather than a
 * timestamp (project dates, quote validity). Parsed as a plain date so a
 * timezone offset can never shift it to the previous day. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "—";
  return new Date(year, month - 1, day).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** A date and time, for anything stored as a real timestamp. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Today, as the `yyyy-mm-dd` an <input type="date"> expects. Built from
 * local date parts rather than toISOString(), which would return
 * yesterday for anyone west of UTC after their local midnight. */
export function todayISO(): string {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

/** `n` days from today, in the same `yyyy-mm-dd` form. */
export function daysFromTodayISO(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

export function formatRelativeTime(isoTimestamp: string): string {
  const then = new Date(isoTimestamp).getTime();
  const now = Date.now();
  const diffSeconds = Math.round((now - then) / 1000);

  if (diffSeconds < 60) return "just now";

  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}
