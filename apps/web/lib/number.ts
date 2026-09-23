/**
 * Post-release remediation §6 — every quantity/dimension/price field in
 * this codebase repeated its own `Number(e.target.value) || 0` (or, on a
 * few screens, stored the raw string and coerced at submit) inline.
 * Centralising it here means a future field can't accidentally regress
 * to a manual-parse path that would mishandle a leading zero — every
 * caller here is a real `type="number"` input, which the browser itself
 * already normalises (typing "05" reads back as "5"), so this is a
 * behaviour-preserving refactor, not a bug fix to the parsing itself.
 */
export function parseNumberInput(raw: string, fallback = 0): number {
  if (raw.trim() === "") return fallback;
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}
