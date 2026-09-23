"use client";

import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import type { SurfaceSearchResult } from "@/types/catalogue";

interface MaterialCatalogueSearchProps {
  id: string;
  value: string;
  onFreeTextChange: (text: string) => void;
  onSelectSurface: (surface: SurfaceSearchResult, thicknessLabel: string, variantId: string | null) => void;
}

/** Post-release remediation (§4) — the stone quote Material field
 * previously offered only a fixed 15-item dropdown; the real Master
 * Catalogue (Plan 03) was reachable solely via a separate /catalogue
 * page and a full-item URL handoff. This searches the same catalogue
 * inline, live, while still behaving as free text: a value never
 * resolved against a catalogue result submits exactly as it did
 * before this search existed. */
export function MaterialCatalogueSearch({
  id,
  value,
  onFreeTextChange,
  onSelectSurface,
}: MaterialCatalogueSearchProps) {
  const [results, setResults] = useState<SurfaceSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const found = await api.searchCatalogueSurfaces({ q: text.trim(), limit: 8 });
        setResults(found);
        setOpen(found.length > 0);
      } catch (err) {
        // A catalogue search failure never blocks free-text entry — the
        // typed value above is already the row's material either way.
        if (!(err instanceof ApiError)) throw err;
        setResults([]);
        setOpen(false);
      } finally {
        setLoading(false);
      }
    }, 300);
  }

  async function handleSelect(surface: SurfaceSearchResult) {
    setOpen(false);
    setResults([]);
    let variantId: string | null = null;
    let thicknessLabel = surface.thicknesses_mm.length > 0 ? `${surface.thicknesses_mm[0]}mm` : "20mm";
    try {
      const detail = await api.getCatalogueSurface(surface.id);
      const firstVariant = detail.variants.find((v) => v.active) ?? detail.variants[0] ?? null;
      if (firstVariant) {
        variantId = firstVariant.id;
        if (firstVariant.thickness_mm) thicknessLabel = `${firstVariant.thickness_mm}mm`;
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
        placeholder="e.g. Calacatta Gold, or a brand like Silestone"
        autoComplete="off"
      />
      {open && (
        <ul className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-border bg-background py-1 text-sm shadow-lg">
          {results.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                className="tap-link block w-full px-3 py-2 text-left hover:bg-surface-hover"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => handleSelect(r)}
              >
                <span className="font-medium text-foreground">{r.canonical_name}</span>
                {(r.brand_name || r.manufacturer_name) && (
                  <span className="ml-2 text-xs text-muted">{r.brand_name ?? r.manufacturer_name}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      {loading && <p className="mt-1 text-xs text-muted">Searching catalogue…</p>}
    </div>
  );
}
