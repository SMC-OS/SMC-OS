"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Checkbox, Field, Input, Select } from "@/components/ui/Field";
import { SearchIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatCurrencyGBP } from "@/lib/utils";
import {
  MATERIAL_FAMILIES,
  MATERIAL_FAMILY_LABELS,
  type CustomMaterialResult,
  type MaterialFamily,
  type SurfaceDetail,
  type SurfaceSearchResult,
} from "@/types/catalogue";

interface CustomMaterialFormState {
  canonical_name: string;
  supplier_name: string;
  manufacturer_name: string;
  material_family: MaterialFamily;
  thickness_mm: string;
  finish: string;
  slab_length_mm: string;
  slab_width_mm: string;
  buy_cost_per_slab: string;
  selling_price_per_slab: string;
  save_to_catalogue: boolean;
}

function blankCustomMaterial(): CustomMaterialFormState {
  return {
    canonical_name: "",
    supplier_name: "",
    manufacturer_name: "",
    material_family: "quartz",
    thickness_mm: "",
    finish: "",
    slab_length_mm: "",
    slab_width_mm: "",
    buy_cost_per_slab: "",
    selling_price_per_slab: "",
    save_to_catalogue: true,
  };
}

/**
 * Sprint 042 (GeoCore Premium OS Plan 03), Task 5 — the Master Materials &
 * Supplier Catalogue read UI. Search and filter across (potentially
 * thousands of) surfaces, backend-paginated/filtered — never a client-side
 * load of the whole catalogue. Selecting a surface opens its detail panel;
 * "Use in this quote" hands the chosen surface + variant to the stone
 * quote builder via query params rather than duplicating its form here.
 */
export default function CataloguePage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();

  const [query, setQuery] = useState("");
  const [materialFamily, setMaterialFamily] = useState<MaterialFamily | "">("");
  const [results, setResults] = useState<SurfaceSearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SurfaceDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedVariantId, setSelectedVariantId] = useState<string>("");

  // Task 3/15/16 — tenant commercial overrides. The global catalogue
  // never carries one universal price; this is the only place a price
  // for this tenant gets written, via PUT /catalogue/surfaces/{id}/
  // override, scoped to this tenant alone.
  const [editingPrice, setEditingPrice] = useState(false);
  const [priceBuyCost, setPriceBuyCost] = useState("");
  const [priceMarkup, setPriceMarkup] = useState("");
  const [priceSellingPrice, setPriceSellingPrice] = useState("");
  const [priceSubmitting, setPriceSubmitting] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);

  // Task 9 — "Can't find your stone? Add a custom material" on every
  // catalogue selector. Never auto-promoted to the global catalogue:
  // "Save to my private catalogue" creates a tenant-private surface only
  // this workspace can see; leaving it off creates nothing durable at
  // all (see app/catalogue/service.py's create_custom_material docstring).
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [customForm, setCustomForm] = useState<CustomMaterialFormState>(blankCustomMaterial());
  const [customSubmitting, setCustomSubmitting] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);
  const [customResult, setCustomResult] = useState<CustomMaterialResult | null>(null);

  const runSearch = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .searchCatalogueSurfaces({
        q: query.trim() || undefined,
        material_family: materialFamily || undefined,
      })
      .then(setResults)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      )
      .finally(() => setLoading(false));
  }, [query, materialFamily]);

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    // Mount/filter-change fetch — same justified pattern as
    // AuthProvider's one-time sync effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    runSearch();
    // Only re-run automatically on the filters below, not on every
    // keystroke into `query` — that has its own explicit "Search" submit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, isAuthenticated, router, materialFamily]);

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    runSearch();
  }

  function openSurface(id: string, keepPriceForm = false) {
    setSelectedId(id);
    setDetail(null);
    setDetailError(null);
    setSelectedVariantId("");
    setDetailLoading(true);
    if (!keepPriceForm) setEditingPrice(false);
    api
      .getCatalogueSurface(id)
      .then((surface) => {
        setDetail(surface);
        if (surface.variants.length > 0) {
          setSelectedVariantId(surface.variants[0].id);
        }
        if (!keepPriceForm) {
          setPriceBuyCost(surface.tenant_override?.buy_cost_per_slab?.toString() ?? "");
          setPriceMarkup(surface.tenant_override?.default_markup_percent?.toString() ?? "");
          setPriceSellingPrice(surface.tenant_override?.selling_price_per_slab?.toString() ?? "");
        }
      })
      .catch((err) =>
        setDetailError(err instanceof ApiError ? err.message : "Something went wrong.")
      )
      .finally(() => setDetailLoading(false));
  }

  async function savePrice(e: React.FormEvent) {
    e.preventDefault();
    if (!detail) return;
    setPriceSubmitting(true);
    setPriceError(null);
    try {
      await api.upsertCatalogueOverride(detail.id, {
        buy_cost_per_slab: priceBuyCost ? Number(priceBuyCost) : null,
        default_markup_percent: priceMarkup ? Number(priceMarkup) : null,
        selling_price_per_slab: priceSellingPrice ? Number(priceSellingPrice) : null,
      });
      openSurface(detail.id, true);
      setEditingPrice(false);
      runSearch();
    } catch (err) {
      setPriceError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setPriceSubmitting(false);
    }
  }

  function useInQuote() {
    if (!detail) return;
    const variant = detail.variants.find((v) => v.id === selectedVariantId) ?? null;
    const params = new URLSearchParams();
    params.set("catalogue_surface_id", detail.id);
    if (variant) params.set("catalogue_variant_id", variant.id);
    params.set("material", detail.canonical_name);
    if (variant?.thickness_mm) params.set("thickness", `${variant.thickness_mm}mm`);
    router.push(`/quotes/new/stone?${params.toString()}`);
  }

  function goToQuoteWithCustomMaterial(result: CustomMaterialResult) {
    const params = new URLSearchParams();
    if (result.surface_id) params.set("catalogue_surface_id", result.surface_id);
    if (result.variant_id) params.set("catalogue_variant_id", result.variant_id);
    params.set("material", result.canonical_name);
    if (customForm.thickness_mm) params.set("thickness", `${customForm.thickness_mm}mm`);
    router.push(`/quotes/new/stone?${params.toString()}`);
  }

  async function handleCustomMaterialSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCustomSubmitting(true);
    setCustomError(null);
    setCustomResult(null);
    try {
      const result = await api.createCustomMaterial({
        canonical_name: customForm.canonical_name,
        supplier_name: customForm.supplier_name || null,
        manufacturer_name: customForm.manufacturer_name || null,
        material_family: customForm.material_family,
        variant: {
          thickness_mm: customForm.thickness_mm ? Number(customForm.thickness_mm) : null,
          finish: customForm.finish || null,
          slab_length_mm: customForm.slab_length_mm ? Number(customForm.slab_length_mm) : null,
          slab_width_mm: customForm.slab_width_mm ? Number(customForm.slab_width_mm) : null,
        },
        buy_cost_per_slab: customForm.buy_cost_per_slab ? Number(customForm.buy_cost_per_slab) : null,
        selling_price_per_slab: customForm.selling_price_per_slab
          ? Number(customForm.selling_price_per_slab)
          : null,
        save_to_catalogue: customForm.save_to_catalogue,
      });
      setCustomResult(result);
      if (result.saved_to_catalogue) {
        runSearch();
      }
    } catch (err) {
      setCustomError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setCustomSubmitting(false);
    }
  }

  if (!isReady || !isAuthenticated) return null;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Master Materials Catalogue
          </h1>
          <p className="mt-1 text-sm text-muted">
            Search suppliers, brands and surfaces to price a stone quote.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setShowCustomForm((v) => !v);
            setCustomResult(null);
            setCustomError(null);
          }}
        >
          Can&apos;t find your stone? Add custom material
        </Button>
      </div>

      {showCustomForm && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Add a custom material</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {customResult ? (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-foreground">
                  <strong>{customResult.canonical_name}</strong>{" "}
                  {customResult.saved_to_catalogue
                    ? "has been saved to your private catalogue."
                    : "was recorded for this quote only — it was not saved anywhere, so search won't find it again."}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" onClick={() => goToQuoteWithCustomMaterial(customResult)}>
                    Use in a stone quote
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowCustomForm(false);
                      setCustomForm(blankCustomMaterial());
                      setCustomResult(null);
                    }}
                  >
                    Close
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCustomMaterialSubmit} className="flex flex-col gap-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Material name" htmlFor="customName" required>
                    <Input
                      id="customName"
                      required
                      value={customForm.canonical_name}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, canonical_name: e.target.value }))
                      }
                      placeholder="e.g. Verde Alpi Granite"
                    />
                  </Field>
                  <Field label="Material family" htmlFor="customFamily" required>
                    <Select
                      id="customFamily"
                      value={customForm.material_family}
                      onChange={(e) =>
                        setCustomForm((f) => ({
                          ...f,
                          material_family: e.target.value as MaterialFamily,
                        }))
                      }
                    >
                      {MATERIAL_FAMILIES.map((fam) => (
                        <option key={fam} value={fam}>
                          {MATERIAL_FAMILY_LABELS[fam]}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Supplier (optional)" htmlFor="customSupplier">
                    <Input
                      id="customSupplier"
                      value={customForm.supplier_name}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, supplier_name: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Manufacturer / brand (optional)" htmlFor="customManufacturer">
                    <Input
                      id="customManufacturer"
                      value={customForm.manufacturer_name}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, manufacturer_name: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Thickness (mm)" htmlFor="customThickness">
                    <Input
                      id="customThickness"
                      type="number"
                      min="0"
                      value={customForm.thickness_mm}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, thickness_mm: e.target.value }))
                      }
                      placeholder="e.g. 20"
                    />
                  </Field>
                  <Field label="Finish (optional)" htmlFor="customFinish">
                    <Input
                      id="customFinish"
                      value={customForm.finish}
                      onChange={(e) => setCustomForm((f) => ({ ...f, finish: e.target.value }))}
                      placeholder="e.g. Polished"
                    />
                  </Field>
                  <Field label="Slab length (mm, optional)" htmlFor="customSlabLength">
                    <Input
                      id="customSlabLength"
                      type="number"
                      min="0"
                      value={customForm.slab_length_mm}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, slab_length_mm: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Slab width (mm, optional)" htmlFor="customSlabWidth">
                    <Input
                      id="customSlabWidth"
                      type="number"
                      min="0"
                      value={customForm.slab_width_mm}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, slab_width_mm: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Your buy cost per slab (optional)" htmlFor="customBuyCost">
                    <Input
                      id="customBuyCost"
                      type="number"
                      min="0"
                      step="0.01"
                      value={customForm.buy_cost_per_slab}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, buy_cost_per_slab: e.target.value }))
                      }
                    />
                  </Field>
                  <Field label="Your selling price per slab (optional)" htmlFor="customSellingPrice">
                    <Input
                      id="customSellingPrice"
                      type="number"
                      min="0"
                      step="0.01"
                      value={customForm.selling_price_per_slab}
                      onChange={(e) =>
                        setCustomForm((f) => ({ ...f, selling_price_per_slab: e.target.value }))
                      }
                    />
                  </Field>
                </div>

                <Checkbox
                  label="Save to my private catalogue, so I can reuse it on future quotes"
                  checked={customForm.save_to_catalogue}
                  onChange={(e) =>
                    setCustomForm((f) => ({ ...f, save_to_catalogue: e.target.checked }))
                  }
                />
                {!customForm.save_to_catalogue && (
                  <p className="text-xs text-muted">
                    Unchecked: this is used for this quote only and is never saved anywhere —
                    not to your private catalogue, and never to the shared global catalogue.
                  </p>
                )}

                {customError && (
                  <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                    {customError}
                  </p>
                )}

                <div className="flex gap-2">
                  <Button type="submit" disabled={customSubmitting}>
                    {customSubmitting ? "Saving…" : "Add material"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => setShowCustomForm(false)}>
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="mb-6">
        <CardContent className="pt-4">
          <form onSubmit={handleSearchSubmit} className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <Field label="Search" htmlFor="catalogueQuery" className="flex-1">
              <Input
                id="catalogueQuery"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. Calacatta, Silestone, Cosentino"
              />
            </Field>
            <Field label="Material family" htmlFor="catalogueFamily" className="sm:w-56">
              <Select
                id="catalogueFamily"
                value={materialFamily}
                onChange={(e) => setMaterialFamily(e.target.value as MaterialFamily | "")}
              >
                <option value="">All families</option>
                {MATERIAL_FAMILIES.map((f) => (
                  <option key={f} value={f}>
                    {MATERIAL_FAMILY_LABELS[f]}
                  </option>
                ))}
              </Select>
            </Field>
            <Button type="submit" disabled={loading}>
              <SearchIcon className="h-4 w-4" />
              {loading ? "Searching…" : "Search"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && (
        <p className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Card>
            <CardHeader>
              <CardTitle>
                {results ? `${results.length} surface${results.length === 1 ? "" : "s"}` : "Surfaces"}
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {results && results.length === 0 && (
                <EmptyState
                  title="No surfaces found"
                  description="Try a different search, or add it as a custom material."
                  action={
                    <Button variant="outline" size="sm" onClick={() => setShowCustomForm(true)}>
                      Add custom material
                    </Button>
                  }
                />
              )}
              <ul className="flex flex-col gap-2">
                {results?.map((surface) => (
                  <li key={surface.id}>
                    <button
                      type="button"
                      onClick={() => openSurface(surface.id)}
                      className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
                        selectedId === surface.id
                          ? "border-accent bg-accent-subtle"
                          : "border-border hover:border-border-strong hover:bg-surface-hover"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-foreground">{surface.canonical_name}</span>
                        <Badge tone="neutral">{MATERIAL_FAMILY_LABELS[surface.material_family]}</Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-muted">
                        {[surface.supplier_name, surface.manufacturer_name, surface.brand_name]
                          .filter(Boolean)
                          .join(" · ") || "No supplier on file"}
                        {surface.is_tenant_private && " · Your private catalogue"}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {surface.discontinued && <Badge tone="danger">Discontinued</Badge>}
                        {!surface.active && <Badge tone="warning">Inactive</Badge>}
                        {surface.has_tenant_price ? (
                          <Badge tone="success">Your price set</Badge>
                        ) : (
                          <Badge tone="neutral">No price set</Badge>
                        )}
                        {surface.thicknesses_mm.length > 0 && (
                          <span className="text-xs text-muted">
                            {surface.thicknesses_mm.map((t) => `${t}mm`).join(", ")}
                          </span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {!selectedId && (
                <p className="text-sm text-muted">Select a surface to see its details.</p>
              )}
              {detailLoading && <p className="text-sm text-muted">Loading…</p>}
              {detailError && <p className="text-sm text-danger">{detailError}</p>}
              {detail && (
                <div className="flex flex-col gap-4">
                  <div>
                    <h3 className="text-lg font-semibold text-foreground">{detail.canonical_name}</h3>
                    <p className="text-sm text-muted">
                      {MATERIAL_FAMILY_LABELS[detail.material_family]}
                      {detail.colour_family ? ` · ${detail.colour_family}` : ""}
                    </p>
                  </div>

                  <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
                    <dt className="text-muted">Supplier</dt>
                    <dd className="text-right text-foreground">{detail.supplier?.name ?? "—"}</dd>
                    <dt className="text-muted">Manufacturer</dt>
                    <dd className="text-right text-foreground">{detail.manufacturer?.name ?? "—"}</dd>
                    <dt className="text-muted">Brand</dt>
                    <dd className="text-right text-foreground">{detail.brand?.name ?? "—"}</dd>
                    <dt className="text-muted">Collection</dt>
                    <dd className="text-right text-foreground">{detail.collection?.name ?? "—"}</dd>
                  </dl>

                  {detail.variants.length > 0 && (
                    <Field label="Thickness / finish / slab size" htmlFor="variantSelect">
                      <Select
                        id="variantSelect"
                        value={selectedVariantId}
                        onChange={(e) => setSelectedVariantId(e.target.value)}
                      >
                        {detail.variants.map((v) => (
                          <option key={v.id} value={v.id}>
                            {[
                              v.thickness_mm ? `${v.thickness_mm}mm` : null,
                              v.finish,
                              v.slab_length_mm && v.slab_width_mm
                                ? `${v.slab_length_mm}x${v.slab_width_mm}mm slab`
                                : null,
                            ]
                              .filter(Boolean)
                              .join(" · ") || "Standard"}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  )}

                  <div className="rounded-lg border border-border bg-surface-hover p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted">
                        Your pricing
                      </p>
                      {!editingPrice && (
                        <button
                          type="button"
                          className="tap-link text-xs text-accent hover:underline"
                          onClick={() => setEditingPrice(true)}
                        >
                          {detail.tenant_override?.resolved_price_per_slab != null
                            ? "Edit price"
                            : "Set your price"}
                        </button>
                      )}
                    </div>

                    {editingPrice ? (
                      <form onSubmit={savePrice} className="mt-2 flex flex-col gap-3">
                        <Field label="Your buy cost per slab" htmlFor="priceBuyCost">
                          <Input
                            id="priceBuyCost"
                            type="number"
                            min="0"
                            step="0.01"
                            value={priceBuyCost}
                            onChange={(e) => setPriceBuyCost(e.target.value)}
                          />
                        </Field>
                        <Field label="Your markup (%)" htmlFor="priceMarkup" hint="Used only when no selling price is set below.">
                          <Input
                            id="priceMarkup"
                            type="number"
                            min="0"
                            step="0.1"
                            value={priceMarkup}
                            onChange={(e) => setPriceMarkup(e.target.value)}
                          />
                        </Field>
                        <Field label="Your selling price per slab" htmlFor="priceSellingPrice" hint="Overrides buy cost + markup when set.">
                          <Input
                            id="priceSellingPrice"
                            type="number"
                            min="0"
                            step="0.01"
                            value={priceSellingPrice}
                            onChange={(e) => setPriceSellingPrice(e.target.value)}
                          />
                        </Field>
                        {priceError && <p className="text-xs text-danger">{priceError}</p>}
                        <div className="flex gap-2">
                          <Button type="submit" size="sm" disabled={priceSubmitting}>
                            {priceSubmitting ? "Saving…" : "Save price"}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => setEditingPrice(false)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </form>
                    ) : detail.tenant_override?.resolved_price_per_slab != null ? (
                      <p className="mt-1 text-lg font-semibold text-foreground">
                        {formatCurrencyGBP(detail.tenant_override.resolved_price_per_slab)}{" "}
                        <span className="text-sm font-normal text-muted">per slab</span>
                      </p>
                    ) : (
                      <p className="mt-1 text-sm text-muted">
                        No price set yet — this is global reference data only. Set your buy
                        cost and markup to price it in a quote.
                      </p>
                    )}
                    {detail.is_tenant_private && (
                      <p className="mt-1 text-xs text-muted">
                        This is a private material in your own catalogue — not visible to
                        other GeoCore workspaces.
                      </p>
                    )}
                  </div>

                  {(detail.source_name || detail.source_url) && (
                    <p className="text-xs text-muted">
                      Source: {detail.source_name ?? detail.source_url}
                      {detail.source_verified_at
                        ? ` · verified ${new Date(detail.source_verified_at).toLocaleDateString("en-GB")}`
                        : ""}
                    </p>
                  )}

                  <Button onClick={useInQuote} disabled={detail.variants.length > 0 && !selectedVariantId}>
                    Use in a stone quote
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
