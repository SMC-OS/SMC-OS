/**
 * Phase A — the stone quote's inline catalogue search must explain an
 * empty result instead of silently showing nothing: an empty catalogue,
 * no match, and a failed search each say so, and each makes clear the
 * typed name still quotes as free text.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const searchCatalogueSurfacesMock = vi.fn();
const getCatalogueStatusMock = vi.fn();
const getCatalogueSurfaceMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      searchCatalogueSurfaces: (...args: unknown[]) => searchCatalogueSurfacesMock(...args),
      getCatalogueStatus: (...args: unknown[]) => getCatalogueStatusMock(...args),
      getCatalogueSurface: (...args: unknown[]) => getCatalogueSurfaceMock(...args),
    },
  };
});

import { ApiError } from "@/lib/api";

import { MaterialCatalogueSearch } from "./MaterialCatalogueSearch";

function Harness() {
  const [value, setValue] = useState("");
  return (
    <MaterialCatalogueSearch id="material" value={value} onFreeTextChange={setValue} onSelectSurface={() => {}} />
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
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("MaterialCatalogueSearch — Phase A empty states", () => {
  it("says the catalogue has no materials yet when reference data is missing", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    getCatalogueStatusMock.mockResolvedValue({ global_surfaces: 0, tenant_surfaces: 0, reference_data_loaded: false });
    render(<Harness />);

    await typeAndSettle("Calacatta");

    expect(screen.getByRole("status")).toHaveTextContent(/catalogue has no materials yet/i);
    expect(screen.getByRole("status")).toHaveTextContent(/quoted as typed/i);
  });

  it("says nothing matched when the catalogue has materials", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    getCatalogueStatusMock.mockResolvedValue({ global_surfaces: 38, tenant_surfaces: 0, reference_data_loaded: true });
    render(<Harness />);

    await typeAndSettle("Zebrawood");

    expect(screen.getByRole("status")).toHaveTextContent("No catalogue match for “Zebrawood”");
  });

  it("only asks for catalogue status once across several empty searches", async () => {
    searchCatalogueSurfacesMock.mockResolvedValue([]);
    getCatalogueStatusMock.mockResolvedValue({ global_surfaces: 38, tenant_surfaces: 0, reference_data_loaded: true });
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

    expect(screen.getByRole("status")).toHaveTextContent(/unavailable right now/i);
    expect(screen.getByRole("textbox")).toHaveValue("Calacatta");
  });
});
