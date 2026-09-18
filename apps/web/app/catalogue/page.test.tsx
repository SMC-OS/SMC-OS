/**
 * Sprint 042 (GeoCore Premium OS Plan 03), Task 20 — component coverage
 * for the Master Materials Catalogue page: search + filters, result
 * display (tenant-price badge, discontinued/inactive), variant selection,
 * price display (set vs. missing — the "never fabricate a price" contract
 * from app/catalogue/service.py's resolve_price_per_slab), "Use in a
 * stone quote" navigation, and the custom material fallback (both
 * save-to-catalogue and quote-only paths).
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  CustomMaterialResult,
  SurfaceDetail,
  SurfaceSearchResult,
} from "@/types/catalogue";

// A stable object, not a fresh literal per call — page.tsx's effect has
// `router` in its dependency array, so a router that isn't referentially
// stable across renders (the way Next's real useRouter is) refires that
// effect on every render, same pitfall app/settings/page.test.tsx notes.
const pushMock = vi.fn();
const replaceMock = vi.fn();
const routerMock = { push: pushMock, replace: replaceMock };
vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({ isAuthenticated: true, isReady: true }),
}));

const searchCatalogueSurfacesMock = vi.fn();
const getCatalogueSurfaceMock = vi.fn();
const createCustomMaterialMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      searchCatalogueSurfaces: (...args: unknown[]) => searchCatalogueSurfacesMock(...args),
      getCatalogueSurface: (...args: unknown[]) => getCatalogueSurfaceMock(...args),
      createCustomMaterial: (...args: unknown[]) => createCustomMaterialMock(...args),
    },
  };
});

import CataloguePage from "./page";

function surface(overrides: Partial<SurfaceSearchResult> = {}): SurfaceSearchResult {
  return {
    id: "surface-1",
    canonical_name: "Calacatta Oro",
    material_family: "quartz",
    colour_family: null,
    supplier_name: "Stone Supplier Ltd",
    manufacturer_name: "Cosentino",
    brand_name: "Silestone",
    collection_name: null,
    active: true,
    discontinued: false,
    is_tenant_private: false,
    thicknesses_mm: [20, 30],
    finishes: ["Polished"],
    has_tenant_price: false,
    ...overrides,
  };
}

function detail(overrides: Partial<SurfaceDetail> = {}): SurfaceDetail {
  return {
    id: "surface-1",
    is_tenant_private: false,
    canonical_name: "Calacatta Oro",
    material_family: "quartz",
    colour_family: null,
    pattern_family: null,
    origin_country: null,
    supplier: { id: "sup-1", name: "Stone Supplier Ltd", slug: "stone-supplier-ltd" },
    manufacturer: { id: "man-1", name: "Cosentino", slug: "cosentino" },
    brand: { id: "brand-1", name: "Silestone", slug: "silestone" },
    collection: null,
    supplier_sku: null,
    manufacturer_sku: null,
    active: true,
    discontinued: false,
    source_name: null,
    source_url: null,
    source_verified_at: null,
    variants: [
      {
        id: "variant-1",
        thickness_mm: 20,
        finish: "Polished",
        slab_length_mm: 3200,
        slab_width_mm: 1600,
        supplier_variant_sku: null,
        active: true,
      },
    ],
    tenant_override: null,
    ...overrides,
  };
}

beforeEach(() => {
  searchCatalogueSurfacesMock.mockReset().mockResolvedValue([surface()]);
  getCatalogueSurfaceMock.mockReset().mockResolvedValue(detail());
  createCustomMaterialMock.mockReset();
  pushMock.mockClear();
  replaceMock.mockClear();
});

afterEach(() => {
  cleanup();
});

describe("CataloguePage — Sprint 042 Plan 03", () => {
  it("searches on mount and lists the results", async () => {
    render(<CataloguePage />);

    await waitFor(() => expect(searchCatalogueSurfacesMock).toHaveBeenCalled());
    expect(await screen.findByText("Calacatta Oro")).toBeInTheDocument();
    expect(screen.getByText(/Stone Supplier Ltd/)).toBeInTheDocument();
    expect(screen.getByText("No price set")).toBeInTheDocument();
  });

  it("shows the tenant-price badge when a surface already has a price", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([surface({ has_tenant_price: true })]);
    render(<CataloguePage />);

    expect(await screen.findByText("Your price set")).toBeInTheDocument();
  });

  it("re-searches with the query and material family filter on submit", async () => {
    render(<CataloguePage />);
    await waitFor(() => expect(searchCatalogueSurfacesMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "Calacatta" } });
    fireEvent.click(screen.getByRole("button", { name: /search/i }));

    await waitFor(() => expect(searchCatalogueSurfacesMock).toHaveBeenCalledTimes(2));
    expect(searchCatalogueSurfacesMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "Calacatta" })
    );
  });

  it("shows an empty state with a custom-material action when nothing matches", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    render(<CataloguePage />);

    expect(await screen.findByText("No surfaces found")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add custom material" })
    ).toBeInTheDocument();
  });

  it("opens a surface's detail panel with its variants and lets the user select one", async () => {
    render(<CataloguePage />);
    fireEvent.click(await screen.findByText("Calacatta Oro"));

    await waitFor(() => expect(getCatalogueSurfaceMock).toHaveBeenCalledWith("surface-1"));
    expect(await screen.findByRole("heading", { name: "Calacatta Oro" })).toBeInTheDocument();
    expect(screen.getByText("Stone Supplier Ltd")).toBeInTheDocument();
    expect(screen.getByLabelText("Thickness / finish / slab size")).toHaveValue("variant-1");
  });

  it("shows the resolved price when the tenant has one set", async () => {
    getCatalogueSurfaceMock.mockResolvedValue(
      detail({
        tenant_override: {
          id: "override-1",
          surface_id: "surface-1",
          surface_variant_id: "variant-1",
          preferred_supplier_id: null,
          supplier_account_ref: null,
          tenant_supplier_sku: null,
          buy_cost_per_slab: 900,
          buy_cost_per_m2: null,
          delivery_cost: null,
          fabrication_rate: null,
          installation_rate: null,
          default_markup_percent: 30,
          target_margin_percent: null,
          selling_price_per_slab: 1170,
          selling_price_per_m2: null,
          stock_status: null,
          lead_time_days: null,
          tenant_active: true,
          private_notes: null,
          resolved_price_per_slab: 1170,
          updated_at: "2026-01-01T00:00:00Z",
        },
      })
    );
    render(<CataloguePage />);
    fireEvent.click(await screen.findByText("Calacatta Oro"));

    expect(await screen.findByText(/£1,170/)).toBeInTheDocument();
  });

  it("never fabricates a price — shows the honest 'no price set' message when the tenant has none", async () => {
    render(<CataloguePage />);
    fireEvent.click(await screen.findByText("Calacatta Oro"));

    expect(await screen.findByText(/No price set yet/)).toBeInTheDocument();
  });

  it("sends the surface, variant, material and thickness to the stone quote builder on 'Use in a stone quote'", async () => {
    render(<CataloguePage />);
    fireEvent.click(await screen.findByText("Calacatta Oro"));
    await screen.findByRole("heading", { name: "Calacatta Oro" });

    fireEvent.click(screen.getByRole("button", { name: "Use in a stone quote" }));

    expect(pushMock).toHaveBeenCalledWith(
      "/quotes/new/stone?catalogue_surface_id=surface-1&catalogue_variant_id=variant-1&material=Calacatta+Oro&thickness=20mm"
    );
  });

  it("adds a custom material and, when saved to the catalogue, re-runs the search", async () => {
    const result: CustomMaterialResult = {
      surface_id: "custom-1",
      variant_id: "custom-variant-1",
      canonical_name: "Verde Alpi Granite",
      saved_to_catalogue: true,
    };
    createCustomMaterialMock.mockResolvedValue(result);
    render(<CataloguePage />);
    await waitFor(() => expect(searchCatalogueSurfacesMock).toHaveBeenCalledTimes(1));

    fireEvent.click(
      screen.getByRole("button", { name: "Can't find your stone? Add custom material" })
    );
    const form = screen.getByRole("button", { name: "Add material" }).closest("form")!;
    fireEvent.change(within(form).getByLabelText("Material name"), {
      target: { value: "Verde Alpi Granite" },
    });
    fireEvent.change(within(form).getByLabelText("Material family"), {
      target: { value: "granite" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add material" }));

    await waitFor(() => expect(createCustomMaterialMock).toHaveBeenCalled());
    expect(createCustomMaterialMock).toHaveBeenCalledWith(
      expect.objectContaining({
        canonical_name: "Verde Alpi Granite",
        material_family: "granite",
        save_to_catalogue: true,
      })
    );
    expect(
      await screen.findByText(/has been saved to your private catalogue/)
    ).toBeInTheDocument();
    await waitFor(() => expect(searchCatalogueSurfacesMock).toHaveBeenCalledTimes(2));
  });

  it("tells the user a quote-only custom material was never saved anywhere", async () => {
    createCustomMaterialMock.mockResolvedValue({
      surface_id: null,
      variant_id: null,
      canonical_name: "One-off Slab",
      saved_to_catalogue: false,
    });
    render(<CataloguePage />);

    fireEvent.click(
      screen.getByRole("button", { name: "Can't find your stone? Add custom material" })
    );
    fireEvent.change(screen.getByLabelText("Material name"), {
      target: { value: "One-off Slab" },
    });
    // "Save to my private catalogue" defaults to checked — uncheck for
    // the quote-only path, Task 9's other branch.
    fireEvent.click(
      screen.getByLabelText("Save to my private catalogue, so I can reuse it on future quotes")
    );
    fireEvent.click(screen.getByRole("button", { name: "Add material" }));

    await waitFor(() => expect(createCustomMaterialMock).toHaveBeenCalled());
    expect(createCustomMaterialMock).toHaveBeenCalledWith(
      expect.objectContaining({ save_to_catalogue: false })
    );
    expect(
      await screen.findByText(/was recorded for this quote only/)
    ).toBeInTheDocument();
  });

  it("surfaces a search error rather than silently showing nothing", async () => {
    const { ApiError } = await import("@/lib/api");
    searchCatalogueSurfacesMock.mockRejectedValue(new ApiError("Something went wrong.", 500));
    render(<CataloguePage />);

    expect(await screen.findByText("Something went wrong.")).toBeInTheDocument();
  });

  it("marks discontinued and inactive surfaces so a fabricator doesn't quote a dead product", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([
      surface({ discontinued: true, active: false }),
    ]);
    render(<CataloguePage />);

    expect(await within(await screen.findByRole("list")).findByText("Discontinued")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });
});
