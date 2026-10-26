/**
 * Phase A — the stone quote's inline catalogue search must explain an
 * empty result instead of silently showing nothing: an empty catalogue,
 * no match, and a failed search each say so, and each makes clear the
 * typed name still quotes as free text.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const searchCatalogueSurfacesMock = vi.fn();
const getCatalogueStatusMock = vi.fn();
const getCatalogueSurfaceMock = vi.fn();
const getCatalogueCompaniesMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getCatalogueCompanies: (...args: unknown[]) =>
        getCatalogueCompaniesMock(...args),
      searchCatalogueSurfaces: (...args: unknown[]) =>
        searchCatalogueSurfacesMock(...args),
      getCatalogueStatus: (...args: unknown[]) =>
        getCatalogueStatusMock(...args),
      getCatalogueSurface: (...args: unknown[]) =>
        getCatalogueSurfaceMock(...args),
    },
  };
});

import { ApiError } from "@/lib/api";

import { MaterialCatalogueSearch } from "./MaterialCatalogueSearch";

function Harness() {
  const [value, setValue] = useState("");
  return (
    <MaterialCatalogueSearch
      id="material"
      value={value}
      onFreeTextChange={setValue}
      onSelectSurface={() => {}}
    />
  );
}

async function typeAndSettle(text: string) {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(350);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  searchCatalogueSurfacesMock.mockReset();
  getCatalogueStatusMock.mockReset();
  getCatalogueSurfaceMock.mockReset();
  getCatalogueCompaniesMock.mockReset().mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("MaterialCatalogueSearch — Phase A empty states", () => {
  it("says the catalogue has no materials yet when reference data is missing", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    getCatalogueStatusMock.mockResolvedValue({
      global_surfaces: 0,
      tenant_surfaces: 0,
      reference_data_loaded: false,
    });
    render(<Harness />);

    await typeAndSettle("Calacatta");

    expect(screen.getByRole("status")).toHaveTextContent(
      /catalogue has no materials yet/i,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/job price/i);
  });

  it("says nothing matched when the catalogue has materials", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    getCatalogueStatusMock.mockResolvedValue({
      global_surfaces: 38,
      tenant_surfaces: 0,
      reference_data_loaded: true,
    });
    render(<Harness />);

    await typeAndSettle("Zebrawood");

    expect(screen.getByRole("status")).toHaveTextContent(
      "No catalogue match for “Zebrawood”",
    );
  });

  it("only asks for catalogue status once across several empty searches", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    getCatalogueStatusMock.mockResolvedValue({
      global_surfaces: 38,
      tenant_surfaces: 0,
      reference_data_loaded: true,
    });
    render(<Harness />);

    await typeAndSettle("Zebra");
    await typeAndSettle("Zebrawood");

    expect(getCatalogueStatusMock).toHaveBeenCalledTimes(1);
  });

  it("never asks for status when the search finds results", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([
      {
        id: "s1",
        canonical_name: "Calacatta Gold",
        material_family: "quartz",
        colour_family: "white",
        supplier_name: null,
        manufacturer_name: "Cosentino",
        brand_name: "Silestone",
        collection_name: null,
        active: true,
        discontinued: false,
        is_tenant_private: false,
        thicknesses_mm: [20],
        finishes: ["Polished"],
        has_tenant_price: false,
      },
    ]);
    render(<Harness />);

    await typeAndSettle("Calacatta");

    expect(screen.getByText("Calacatta Gold")).toBeInTheDocument();
    expect(getCatalogueStatusMock).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("says search is unavailable when the API fails, without blocking typing", async () => {
    searchCatalogueSurfacesMock.mockRejectedValue(new ApiError("boom", 500));
    render(<Harness />);

    await typeAndSettle("Calacatta");

    expect(screen.getByRole("status")).toHaveTextContent(
      /unavailable right now/i,
    );
    expect(screen.getByRole("textbox")).toHaveValue("Calacatta");
  });
});

it("shows the workspace material photograph in the selection card", async () => {
  searchCatalogueSurfacesMock.mockResolvedValue([
    {
      id: "photo-stone",
      canonical_name: "Photo Quartz",
      thicknesses_mm: [20],
      image_url: "https://example.com/quartz.jpg",
    },
  ]);
  render(<Harness />);
  await typeAndSettle("Photo");
  expect(screen.getByRole("img", { name: "Photo Quartz" })).toHaveAttribute(
    "src",
    "https://example.com/quartz.jpg",
  );
});

it("explains an expired session instead of promising that an unpriced name can be quoted", async () => {
  searchCatalogueSurfacesMock.mockRejectedValue(
    new ApiError("Sign in required", 401),
  );
  render(<Harness />);
  await typeAndSettle("Marble");
  expect(screen.getByRole("status")).toHaveTextContent(/sign in again/i);
  expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
    "target",
    "_blank",
  );
  expect(screen.getByRole("textbox")).toHaveValue("Marble");
});

it("browses the catalogue without a search term and applies the material type filter", async () => {
  searchCatalogueSurfacesMock.mockResolvedValue([
    { id: "marble-1", canonical_name: "Browse Marble", thicknesses_mm: [20] },
  ]);
  render(<Harness />);
  fireEvent.change(screen.getByLabelText("Material type"), {
    target: { value: "marble" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Browse materials" }));
  });
  expect(
    screen.getByRole("button", { name: /Browse Marble/ }),
  ).toBeInTheDocument();
  expect(searchCatalogueSurfacesMock).toHaveBeenCalledWith(
    expect.objectContaining({
      material_family: "marble",
      limit: 24,
    }),
  );
});

it("filters by company and loads materials beyond the first page", async () => {
  getCatalogueCompaniesMock.mockResolvedValue([
    { id: "noble-1", name: "NobleStone", kind: "supplier" },
  ]);
  searchCatalogueSurfacesMock
    .mockResolvedValueOnce(
      Array.from({ length: 24 }, (_, i) => ({
        id: `s-${i}`,
        canonical_name: `Stone ${i}`,
        supplier_name: "NobleStone",
        thicknesses_mm: [],
      })),
    )
    .mockResolvedValueOnce([
      {
        id: "last",
        canonical_name: "Carrara Cashmere",
        supplier_name: "NobleStone",
        thicknesses_mm: [],
      },
    ]);
  await act(async () => {
    render(<Harness />);
  });
  await act(async () => {
    fireEvent.change(screen.getByLabelText("Company / supplier"), {
      target: { value: "supplier:noble-1" },
    });
  });
  expect(searchCatalogueSurfacesMock).toHaveBeenLastCalledWith(
    expect.objectContaining({ supplier_id: "noble-1", limit: 24, offset: 0 }),
  );
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: "Load more materials" }),
    );
  });
  expect(searchCatalogueSurfacesMock).toHaveBeenLastCalledWith(
    expect.objectContaining({ supplier_id: "noble-1", offset: 24 }),
  );
  expect(
    screen.getByRole("button", { name: /Carrara Cashmere/ }),
  ).toBeInTheDocument();
  expect(screen.getByText("Stone 0", { exact: true })).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Load more materials" }),
  ).not.toBeInTheDocument();
});
