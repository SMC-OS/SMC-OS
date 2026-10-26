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
  type SurfaceVariant,
} from "@/types/catalogue";

interface MaterialCatalogueSearchProps {
  id: string;
  value: string;
  onFreeTextChange: (text: string) => void;
  onSelectSurface: (
    surface: SurfaceSearchResult,
    thicknessLabel: string,
    variantId: string | null,
    variant: SurfaceVariant | null,
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
  const [company, setCompany] = useState("");
  const [companies, setCompanies] = useState<
    { id: string; name: string; kind: "supplier" | "manufacturer" }[]
  >([]);
  const [canLoadMore, setCanLoadMore] = useState(false);
  const [browseMode, setBrowseMode] = useState(false);
  const requestVersion = useRef(0);
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

  useEffect(() => {
    api
      .getCatalogueCompanies?.()
      .then(setCompanies)
      .catch(() => setCompanies([]));
  }, []);

  async function searchMaterials(
    text: string,
    selectedFamily = family,
    selectedCompany = company,
    offset = 0,
    browse = false,
  ) {
    const version = ++requestVersion.current;
    const [kind, companyId] = selectedCompany.split(":");
    setLoading(true);
    try {
      const found = await api.searchCatalogueSurfaces({
        q: browse ? undefined : text.trim() || undefined,
        material_family: selectedFamily || undefined,
        supplier_id: kind === "supplier" ? companyId : undefined,
        manufacturer_id: kind === "manufacturer" ? companyId : undefined,
        limit: 24,
        offset,
      });
      if (version !== requestVersion.current) return;
      setResults((previous) => (offset ? [...previous, ...found] : found));
      setCanLoadMore(found.length === 24);
      setOpen(offset > 0 || found.length > 0);
      setOutcome(
        found.length || offset ? "results" : await explainEmptyResult(),
      );
    } catch (err) {
      if (version !== requestVersion.current) return;
      if (!offset) setResults([]);
      setOpen(offset > 0);
      setCanLoadMore(false);
      setOutcome(
        err instanceof ApiError && err.status === 401
          ? "sign_in"
          : "unavailable",
      );
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }

  function handleChange(text: string) {
    onFreeTextChange(text);
    setBrowseMode(false);
    ++requestVersion.current;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setResults([]);
    setOpen(false);
    setOutcome("idle");
    setCanLoadMore(false);
    if (text.trim().length < 2) {
      setLoading(false);
      return;
    }
    debounceRef.current = setTimeout(() => void searchMaterials(text), 300);
  }

  function browseMaterials() {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setBrowseMode(true);
    void searchMaterials("", family, company, 0, true);
  }

  async function handleSelect(surface: SurfaceSearchResult) {
    setOpen(false);
    setResults([]);
    setOutcome("idle");
    let variantId: string | null = null;
    let selectedVariant: SurfaceVariant | null = null;
    let thicknessLabel =
      surface.thicknesses_mm.length > 0
        ? `${surface.thicknesses_mm[0]}mm`
        : "20mm";
    try {
      const detail = await api.getCatalogueSurface(surface.id);
      const firstVariant =
        detail.variants.find((v) => v.active) ?? detail.variants[0] ?? null;
      selectedVariant = firstVariant;
      if (firstVariant) {
        variantId = firstVariant.id;
        if (firstVariant.thickness_mm)
          thicknessLabel = `${firstVariant.thickness_mm}mm`;
      }
    } catch {
      // Fall back to the surface alone (no specific variant) rather than
      // blocking selection on a second failed request.
    }
    onSelectSurface(surface, thicknessLabel, variantId, selectedVariant);
  }

  const groups = new Map<string, SurfaceSearchResult[]>();
  for (const surface of results) {
    const name =
      [surface.supplier_name, surface.manufacturer_name, surface.brand_name]
        .filter(Boolean)
        .join(" · ") || "Supplier not specified";
    groups.set(name, [...(groups.get(name) ?? []), surface]);
  }

  return (
    <div className="relative">
      <Input
        id={id}
        required
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
          onChange={(e) => {
            const next = e.target.value as MaterialFamily | "";
            setFamily(next);
            if (debounceRef.current) clearTimeout(debounceRef.current);
            void searchMaterials(value, next, company, 0, browseMode);
          }}
        >
          <option value="">All material types</option>
          {MATERIAL_FAMILIES.map((type) => (
            <option key={type} value={type}>
              {MATERIAL_FAMILY_LABELS[type]}
            </option>
          ))}
        </Select>
        <label className="sr-only" htmlFor={`${id}-company`}>
          Company / supplier
        </label>
        <Select
          id={`${id}-company`}
          className="min-w-0 flex-1"
          value={company}
          onChange={(event) => {
            const next = event.target.value;
            setCompany(next);
            if (debounceRef.current) clearTimeout(debounceRef.current);
            setBrowseMode(true);
            void searchMaterials("", family, next, 0, true);
          }}
        >
          <option value="">All companies</option>
          {companies.map((entry) => (
            <option
              key={`${entry.kind}:${entry.id}`}
              value={`${entry.kind}:${entry.id}`}
            >
              {entry.name}
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
        <ul className="mt-3 flex max-h-96 flex-col gap-4 overflow-auto rounded-lg border border-border bg-background p-3 text-sm">
          {Array.from(groups, ([name, surfaces]) => (
            <li key={name}>
              <h3 className="mb-2 font-semibold">{name}</h3>
              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {surfaces.map((r) => (
                  <li key={r.id} className="min-w-0">
                    <button
                      type="button"
                      className="block h-full w-full overflow-hidden rounded-lg border border-border text-left hover:border-accent hover:bg-surface-hover"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => handleSelect(r)}
                    >
                      <MaterialPhoto
                        url={r.image_url}
                        name={r.canonical_name}
                      />
                      <span className="block break-words px-3 py-2 font-medium text-foreground">
                        {r.canonical_name}
                      </span>
                      {!r.has_tenant_price && (
                        <span className="block px-3 pb-2 text-xs text-muted">
                          Choose this material; set your job price in Pricing
                        </span>
                      )}
                      {(r.supplier_name ||
                        r.brand_name ||
                        r.manufacturer_name) && (
                        <span className="block px-3 pb-3 text-xs text-muted">
                          {[r.supplier_name, r.manufacturer_name, r.brand_name]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {open && canLoadMore && (
        <button
          type="button"
          disabled={loading}
          className="mt-3 text-sm text-accent underline"
          onClick={() =>
            void searchMaterials(
              value,
              family,
              company,
              results.length,
              browseMode,
            )
          }
        >
          Load more materials
        </button>
      )}
      <p className="mt-1 text-xs text-muted" role="status" aria-live="polite">
        {loading
          ? "Searching catalogue…"
          : outcome === "sign_in"
            ? "Sign in again to browse your workspace catalogue. Your typed material is kept."
            : outcome === "no_match"
              ? `No catalogue match for “${value.trim()}” — keep the name, set your job price in the Pricing step.`
              : outcome === "catalogue_empty"
                ? "The material catalogue has no materials yet — enter a material name; set your job price in the Pricing step."
                : outcome === "unavailable"
                  ? "Catalogue search is unavailable right now. Your typed name is kept; set your job price in the Pricing step."
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
