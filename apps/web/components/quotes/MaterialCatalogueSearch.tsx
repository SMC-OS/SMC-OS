"use client";

import { useEffect, useRef, useState } from "react";

import { Input, Select } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import {
  MATERIAL_FAMILIES,
  MATERIAL_FAMILY_LABELS,
  type MaterialFamily,
  type CatalogueStatus,
  type SurfaceSearchResult,
} from "@/types/catalogue";

interface MaterialCatalogueSearchProps {
  id: string;
  value: string;
  onFreeTextChange: (text: string) => void;
  onSelectSurface: (
    surface: SurfaceSearchResult,
    thicknessLabel: string,
    variantId: string | null,
  ) => void;
}

/** Post-release remediation (§4) — the stone quote Material field
 * previously offered only a fixed 15-item dropdown; the real Master
 * Catalogue (Plan 03) was reachable solely via a separate /catalogue
 * page and a full-item URL handoff. This searches the same catalogue
 * inline, live, while still behaving as free text: a value never
 * resolved against a catalogue result submits exactly as it did
 * before this search existed.
 *
 * Phase A — a search that finds nothing now says why: the shared
 * catalogue has not been loaded, nothing matched, or the search itself
 * failed. Every case is explicit that the typed text still quotes as
 * free text, so an empty catalogue never looks like a broken form. */
type Outcome =
  | "idle"
  | "results"
  | "no_match"
  | "catalogue_empty"
  | "sign_in"
  | "unavailable";

export function MaterialCatalogueSearch({
  id,
  value,
  onFreeTextChange,
  onSelectSurface,
}: MaterialCatalogueSearchProps) {
  const [family, setFamily] = useState<MaterialFamily | "">("");
  const [results, setResults] = useState<SurfaceSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>("idle");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Fetched once, only when a search first comes back empty — a search
  // that finds results never needs it.
  const statusRef = useRef<CatalogueStatus | null>(null);

  async function explainEmptyResult(): Promise<Outcome> {
    if (!statusRef.current) {
      try {
        statusRef.current = await api.getCatalogueStatus();
      } catch {
        return "no_match";
      }
    }
    const status = statusRef.current;
    return status.global_surfaces + status.tenant_surfaces === 0
      ? "catalogue_empty"
      : "no_match";
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  function handleChange(text: string) {
    onFreeTextChange(text);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (text.trim().length < 2) {
      setResults([]);
      setOpen(false);
      setOutcome("idle");
      return;
    }
    setOutcome("idle");
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const found = await api.searchCatalogueSurfaces({
          q: text.trim(),
          limit: 24,
          material_family: family || undefined,
        });
        setResults(found);
        setOpen(found.length > 0);
        setOutcome(found.length > 0 ? "results" : await explainEmptyResult());
      } catch (err) {
        // A catalogue search failure never blocks free-text entry — the
        // typed value above is already the row's material either way.
        if (!(err instanceof ApiError)) throw err;
        setResults([]);
        setOpen(false);
        setOutcome(err.status === 401 ? "sign_in" : "unavailable");
      } finally {
        setLoading(false);
      }
    }, 300);
  }

  async function browseMaterials() {
    setLoading(true);
    try {
      const found = await api.searchCatalogueSurfaces({
        material_family: family || undefined,
        limit: 24,
      });
      setResults(found);
      setOpen(found.length > 0);
      setOutcome(found.length ? "results" : await explainEmptyResult());
    } catch (err) {
      setResults([]);
      setOpen(false);
      setOutcome(
        err instanceof ApiError && err.status === 401
          ? "sign_in"
          : "unavailable",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSelect(surface: SurfaceSearchResult) {
    setOpen(false);
    setResults([]);
    setOutcome("idle");
    let variantId: string | null = null;
    let thicknessLabel =
      surface.thicknesses_mm.length > 0
        ? `${surface.thicknesses_mm[0]}mm`
        : "20mm";
    try {
      const detail = await api.getCatalogueSurface(surface.id);
      const firstVariant =
        detail.variants.find((v) => v.active) ?? detail.variants[0] ?? null;
      if (firstVariant) {
        variantId = firstVariant.id;
        if (firstVariant.thickness_mm)
          thicknessLabel = `${firstVariant.thickness_mm}mm`;
      }
    } catch {
      // Fall back to the surface alone (no specific variant) rather than
      // blocking selection on a second failed request.
    }
    onSelectSurface(surface, thicknessLabel, variantId);
  }

  return (
    <div className="relative">
      <Input
        id={id}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => setOpen(results.length > 0)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="e.g. Calacatta Gold, white quartz, or Silestone"
        autoComplete="off"
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <label className="sr-only" htmlFor={`${id}-family`}>
          Material type
        </label>
        <Select
          id={`${id}-family`}
          className="min-w-0 flex-1"
          value={family}
          onChange={(e) => setFamily(e.target.value as MaterialFamily | "")}
        >
          <option value="">All material types</option>
          {MATERIAL_FAMILIES.map((type) => (
            <option key={type} value={type}>
              {MATERIAL_FAMILY_LABELS[type]}
            </option>
          ))}
        </Select>
        <button
          type="button"
          className="rounded-lg border border-border px-3 py-2 text-sm text-foreground"
          disabled={loading}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => void browseMaterials()}
        >
          Browse materials
        </button>
      </div>
      {open && (
        <ul className="mt-3 grid max-h-96 grid-cols-1 gap-3 overflow-auto rounded-lg border border-border bg-background p-3 text-sm sm:grid-cols-2">
          {results.map((r) => (
            <li key={r.id} className="min-w-0">
              <button
                type="button"
                className="block h-full w-full overflow-hidden rounded-lg border border-border text-left hover:border-accent hover:bg-surface-hover"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => handleSelect(r)}
              >
                <MaterialPhoto url={r.image_url} name={r.canonical_name} />
                <span className="block break-words px-3 py-2 font-medium text-foreground">
                  {r.canonical_name}
                </span>
                {!r.has_tenant_price && (
                  <span className="block px-3 pb-2 text-xs text-muted">
                    Price needed — enter your slab price after selecting
                  </span>
                )}
                {(r.brand_name || r.manufacturer_name) && (
                  <span className="block px-3 pb-3 text-xs text-muted">
                    {r.brand_name ?? r.manufacturer_name}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1 text-xs text-muted" role="status" aria-live="polite">
        {loading
          ? "Searching catalogue…"
          : outcome === "sign_in"
            ? "Sign in again to browse your workspace catalogue. Your typed material is kept."
            : outcome === "no_match"
              ? `No catalogue match for “${value.trim()}” — keep the name and enter your own slab price below.`
              : outcome === "catalogue_empty"
                ? "The material catalogue has no materials yet — enter a material name and your own slab price below."
                : outcome === "unavailable"
                  ? "Catalogue search is unavailable right now. Your typed name is kept; an unpriced material needs your own slab price."
                  : null}
      </p>
      {outcome === "sign_in" && (
        <a
          className="mt-2 inline-block text-sm text-accent underline"
          href="/login"
          target="_blank"
          rel="noopener noreferrer"
        >
          Sign in in a new tab
        </a>
      )}
    </div>
  );
}

function MaterialPhoto({ url, name }: { url?: string | null; name: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  return (
    <div className="flex h-32 items-center justify-center bg-surface-hover">
      {url && failedUrl !== url ? (
        // eslint-disable-next-line @next/next/no-img-element -- workspace HTTPS sources are validated by the API; no server-side image proxy.
        <img
          src={url}
          alt={name}
          className="h-full w-full object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        <span className="text-xs text-muted">Photo not supplied</span>
      )}
    </div>
  );
}
