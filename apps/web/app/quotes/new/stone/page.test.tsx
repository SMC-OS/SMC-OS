/**
 * Sprint 033 (Workstream C) — multi-item quote editor: add/remove/
 * duplicate items, submit structured items, and the AI draft flow
 * showing multiple interpreted items with per-item match status before
 * anything is added to the form.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import NewQuotePage from "./page";
import { writeQuoteCustomMaterial } from "@/lib/quote-custom-material";

// Sprint 042 (GeoCore Premium OS Plan 03) — the page now reads
// catalogue_surface_id/catalogue_variant_id/material/thickness from the
// URL on mount (arriving from /catalogue's "Use in a stone quote"). Empty
// by default, matching every existing test in this file that doesn't
// arrive via the catalogue; the catalogue-integration tests below set it.
let currentSearch = "";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(currentSearch),
}));

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isReady: true,
    tenantName: "Pytest Co",
    role: "Owner",
    userId: "owner-1",
    login: vi.fn(),
    signup: vi.fn(),
    acceptInvite: vi.fn(),
    logout: vi.fn(),
  }),
}));

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function makeQuoteItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "item-1",
    position: 0,
    item_type: "worktop",
    material: "Calacatta Oro",
    thickness: "20mm",
    quantity: 1,
    length_mm: 2400,
    width_mm: 600,
    thickness_mm: null,
    unit_input: "mm",
    notes: null,
    price_per_slab: 2350,
    slabs: 1,
    line_total: 2350,
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url.includes("/customers?")) {
      return jsonResponse([]);
    }
    if (url.endsWith("/customers/customer-outside-page")) {
      return jsonResponse({
        id: "customer-outside-page",
        name: "Sarah Whitfield",
        customer_type: "individual",
        created_at: new Date().toISOString(),
      });
    }
    if (url.endsWith("/quotes/ai-draft") && init?.method === "POST") {
      const parsedBody = JSON.parse(String(init.body));
      if (parsedBody.text === "missing product") {
        return jsonResponse({
          customer: null,
          postcode: null,
          items: [
            {
              item_type: "worktop",
              material: null,
              material_raw: "SuperGalaxy Diamond Quartz",
              material_match_status: "not_found",
              material_candidates: [],
              thickness: null,
              quantity: 1,
              length_mm: 2400,
              width_mm: 600,
              thickness_mm: null,
              unit_input: "mm",
              warnings: [
                "Material 'SuperGalaxy Diamond Quartz' wasn't recognised — pick one manually.",
              ],
            },
          ],
          warnings: [],
        });
      }
      return jsonResponse({
        customer: "Sarah Whitfield",
        postcode: null,
        items: [
          {
            item_type: "worktop",
            material: "Calacatta Oro",
            material_raw: null,
            material_match_status: "found",
            material_candidates: [],
            thickness: "20mm",
            quantity: 1,
            length_mm: 2400,
            width_mm: 600,
            thickness_mm: 20,
            unit_input: "mm",
            warnings: [],
          },
        ],
        warnings: [],
      });
    }
    if (url.includes("/catalogue/surfaces?")) {
      const parsed = new URL(url, "http://localhost");
      const q = parsed.searchParams.get("q") ?? "";
      if (
        !q.toLowerCase().includes("silestone") &&
        !q.toLowerCase().includes("calacatta")
      ) {
        return jsonResponse([]);
      }
      return jsonResponse([
        {
          id: "surface-search-1",
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
          thicknesses_mm: [20, 30],
          finishes: ["Polished"],
          has_tenant_price: false,
        },
      ]);
    }
    if (url.endsWith("/catalogue/surfaces/surface-search-1")) {
      return jsonResponse({
        id: "surface-search-1",
        is_tenant_private: false,
        canonical_name: "Calacatta Gold",
        material_family: "quartz",
        colour_family: "white",
        pattern_family: null,
        origin_country: null,
        supplier: null,
        manufacturer: { id: "mfr-1", name: "Cosentino", slug: "cosentino" },
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
            id: "variant-search-1",
            thickness_mm: 20,
            finish: "Polished",
            slab_length_mm: 3200,
            slab_width_mm: 1600,
            supplier_variant_sku: null,
            active: true,
          },
        ],
        tenant_override: null,
      });
    }
    if (url.endsWith("/quote") && init?.method === "POST") {
      const parsedBody = JSON.parse(String(init.body));
      const items = (parsedBody.items ?? []).map(
        (item: Record<string, unknown>, i: number) =>
          makeQuoteItem({ id: `item-${i}`, ...item }),
      );
      return jsonResponse({
        customer: parsedBody.customer,
        material: items[0]?.material ?? "Calacatta Oro",
        thickness: items[0]?.thickness ?? "20mm",
        slabs: items.length,
        price_per_slab: 2350,
        items,
        price_before_vat: 2350 * items.length,
        vat: 470 * items.length,
        total: 2820 * items.length,
        id: "quote-1",
        customer_id: null,
        created_at: new Date().toISOString(),
      });
    }
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
});

afterEach(() => {
  cleanup();
  clearToken();
  vi.unstubAllGlobals();
  currentSearch = "";
});

describe("NewQuotePage — multi-item editor (Sprint 033)", () => {
  it("loads the forwarded customer when it is outside the initial customer page", async () => {
    currentSearch = "customer=customer-outside-page";
    renderEditor();

    expect(await screen.findByLabelText("Customer name")).toHaveValue(
      "Sarah Whitfield",
    );
    const customerSelect = await screen.findByLabelText(
      "Link to existing customer (optional)",
    );
    expect(customerSelect).toHaveValue("customer-outside-page");
    expect(
      within(customerSelect).getByRole("option", {
        name: "Sarah Whitfield",
      }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/customers\/customer-outside-page$/),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("starts with a single item row and submits it as `items`", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.clear(screen.getByLabelText(/width\/depth \(mm\)/i));
    await userEvent.type(screen.getByLabelText(/width\/depth \(mm\)/i), "600");

    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/quote"),
        expect.objectContaining({ method: "POST" }),
      );
    });

    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items).toHaveLength(1);
    expect(body.items[0].length_mm).toBe(2400);
    expect(body.items[0].width_mm).toBe(600);
  });

  it("adds a second item and submits both", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(
      screen.getAllByLabelText(/^length \(mm\)$/i)[0],
      "2400",
    );

    await userEvent.click(screen.getByRole("button", { name: /\+ add item/i }));
    expect(screen.getByText("Item 2")).toBeInTheDocument();

    const lengthInputs = screen.getAllByLabelText(/^length \(mm\)$/i);
    expect(lengthInputs).toHaveLength(2);
    await userEvent.type(lengthInputs[1], "1200");

    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items).toHaveLength(2);
  });

  it("duplicates an item, producing a third identical row", async () => {
    renderEditor();

    expect(screen.getByText("Item 1")).toBeInTheDocument();
    expect(screen.queryByText("Item 2")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /duplicate/i }));

    expect(screen.getByText("Item 1")).toBeInTheDocument();
    expect(screen.getByText("Item 2")).toBeInTheDocument();
  });

  it("removes an item but never below one row", async () => {
    renderEditor();

    const removeButton = screen.getByRole("button", { name: /remove/i });
    expect(removeButton).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /\+ add item/i }));
    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    expect(removeButtons[0]).toBeEnabled();

    await userEvent.click(removeButtons[0]);
    expect(screen.queryByText("Item 2")).not.toBeInTheDocument();
  });

  it("shows the resolved material for a confident AI match and lets the user apply it", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByPlaceholderText(/calacatta oro 20mm/i),
      "Calacatta Oro 20mm, 2400 x 600mm, customer Sarah Whitfield",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /generate draft/i }),
    );

    expect(await screen.findByText(/interpreted 1 item/i)).toBeInTheDocument();
    // "Calacatta Oro" also appears as a plain <option> in the material
    // dropdown — scope to the actual match-status badge, not just any
    // element with that text.
    const badgeMatch = screen
      .getAllByText("Calacatta Oro")
      .find((el) => el.tagName !== "OPTION");
    expect(badgeMatch).toBeTruthy();
    await userEvent.click(
      screen.getByRole("button", { name: /use these items/i }),
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/^length \(mm\)$/i)).toHaveValue(2400);
    });
    expect(screen.getByLabelText(/width\/depth \(mm\)/i)).toHaveValue(600);
    expect(screen.getByDisplayValue("Sarah Whitfield")).toBeInTheDocument();
  });

  it("shows not-found for a missing product without fabricating a match", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByPlaceholderText(/calacatta oro 20mm/i),
      "missing product",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /generate draft/i }),
    );

    expect(
      await screen.findByText(/not found: SuperGalaxy Diamond Quartz/i),
    ).toBeInTheDocument();
  });

  it("renders per-item results after a successful multi-item calculation", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(
      screen.getAllByLabelText(/^length \(mm\)$/i)[0],
      "2400",
    );

    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    const resultHeading = await screen.findByText(/quote for sarah whitfield/i);
    const card = resultHeading.closest("div")?.parentElement as HTMLElement;
    expect(within(card).getByText(/worktop/i)).toBeInTheDocument();
  });
});

describe("NewQuotePage — Master Catalogue integration (Sprint 042, Plan 03)", () => {
  it("pre-fills the first item from the catalogue query params and submits the linkage", async () => {
    currentSearch =
      "catalogue_surface_id=surface-1&catalogue_variant_id=variant-1&material=Calacatta+Oro&thickness=20mm";
    renderEditor();

    expect(screen.getByText("From catalogue")).toBeInTheDocument();
    expect(screen.getByText("Calacatta Oro")).toBeInTheDocument();
    expect(screen.getByText("20mm")).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/quote"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].catalogue_surface_id).toBe("surface-1");
    expect(body.items[0].catalogue_variant_id).toBe("variant-1");
    expect(body.items[0].material).toBe("Calacatta Oro");
  });

  it("clears the catalogue link and reverts to free-text pickers when 'Change' is clicked", async () => {
    currentSearch =
      "catalogue_surface_id=surface-1&material=Calacatta+Oro&thickness=20mm";
    renderEditor();

    expect(screen.getByText("From catalogue")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /change/i }));

    expect(screen.queryByText("From catalogue")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Material")).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].catalogue_surface_id).toBeNull();
  });

  it("submits null catalogue linkage for an ordinary, non-catalogue item", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].catalogue_surface_id).toBeNull();
    expect(body.items[0].catalogue_variant_id).toBeNull();
  });

  it("offers a link to browse the Master Catalogue for an authenticated user", () => {
    renderEditor();
    expect(
      screen.getByRole("link", { name: /browse master catalogue/i }),
    ).toHaveAttribute("href", "/catalogue");
  });
});

describe("NewQuotePage — post-release remediation (§4): inline catalogue material search", () => {
  it("searches the catalogue as the user types and links the chosen surface on selection", async () => {
    renderEditor();

    const materialField = screen.getByLabelText("Material");
    await userEvent.type(materialField, "Silestone");

    const suggestion = await screen.findByRole("button", {
      name: /calacatta gold/i,
    });
    await userEvent.click(suggestion);

    await waitFor(() => {
      expect(screen.getByText("From catalogue")).toBeInTheDocument();
    });
    expect(screen.getByText("Calacatta Gold")).toBeInTheDocument();
    expect(screen.getByText("20mm")).toBeInTheDocument();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].catalogue_surface_id).toBe("surface-search-1");
    expect(body.items[0].catalogue_variant_id).toBe("variant-search-1");
  });

  it("keeps typed free text as the material with no catalogue link when nothing is selected", async () => {
    renderEditor();

    const materialField = screen.getByLabelText("Material");
    await userEvent.clear(materialField);
    await userEvent.type(materialField, "Some Unlisted Stone");

    expect(materialField).toHaveValue("Some Unlisted Stone");
    expect(screen.queryByText("From catalogue")).not.toBeInTheDocument();
  });
});

describe("NewQuotePage — post-release remediation (§4): layout picker and extras", () => {
  it("lets the user pick a visual layout and records it on the item's notes", async () => {
    renderEditor();

    await userEvent.selectOptions(
      screen.getByLabelText("Worktop layout"),
      "l_shape",
    );
    await userEvent.type(screen.getByLabelText("Piece B length (mm)"), "1800");
    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].notes).toContain("L-shape");
  });

  it("submits every measured U-shape plus island piece with its own dimensions", async () => {
    renderEditor();
    await userEvent.selectOptions(
      screen.getByLabelText("Worktop layout"),
      "u_shape_island",
    );
    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Pilot Test Customer",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    for (const [label, length] of [
      ["B", "1800"],
      ["C", "1600"],
      ["D", "2100"],
    ]) {
      await userEvent.type(
        screen.getByLabelText(`Piece ${label} length (mm)`),
        length,
      );
    }
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) => String(u).endsWith("/quote")),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(
      body.items.map((item: { length_mm: number }) => item.length_mm),
    ).toEqual([2400, 1800, 1600, 2100]);
    expect(body.items[3].item_type).toBe("island");
    expect(body.items[3].notes).toContain("Piece D");
  });

  it("lets the user pick extras and records them on the item's notes", async () => {
    renderEditor();

    await userEvent.click(screen.getByLabelText(/sink \/ hob cutout/i));
    await userEvent.click(screen.getByLabelText(/polished edge/i));
    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].notes).toContain("Sink / hob cutout");
    expect(body.items[0].notes).toContain("Polished edge");
  });

  it("sends null notes when no layout or extras are chosen", async () => {
    renderEditor();

    await userEvent.type(
      screen.getByLabelText(/customer name/i),
      "Sarah Whitfield",
    );
    await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
    await userEvent.click(
      screen.getByRole("button", { name: /calculate quote/i }),
    );

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u]) =>
        String(u).endsWith("/quote"),
      );
      expect(call).toBeTruthy();
    });
    const call = fetchMock.mock.calls.find(([u]) =>
      String(u).endsWith("/quote"),
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.items[0].notes).toBeNull();
  });

  it("keeps the free-text thickness dropdown limited to what the legacy material table actually prices", () => {
    // 12mm stone is reachable through a catalogue-linked selection
    // instead (its thickness comes from the chosen surface's real
    // variant) — the free-text dropdown must never offer a combination
    // the legacy material table (app/materials/seed.py) can't resolve.
    renderEditor();
    const thicknessSelect = screen.getByLabelText(
      "Thickness",
    ) as HTMLSelectElement;
    const values = Array.from(thicknessSelect.options).map((o) => o.value);
    expect(values).toEqual(["20mm", "30mm"]);
  });
});

it("keeps a quote-only custom material in the submitted stone quote", async () => {
  const custom = {
    canonical_name: "Synthetic private quartz",
    material_family: "quartz" as const,
    variant: { thickness_mm: 20, slab_length_mm: 3000, slab_width_mm: 1400 },
    buy_cost_per_slab: 400,
    selling_price_per_slab: 600,
    save_to_catalogue: false,
  };
  currentSearch = `custom_material_id=${writeQuoteCustomMaterial(custom)}`;
  renderEditor();
  expect(await screen.findByText("Synthetic private quartz")).toBeVisible();
  await userEvent.type(
    screen.getByLabelText("Customer name"),
    "Synthetic customer",
  );
  await userEvent.type(screen.getByLabelText("Length (mm)"), "2400");
  await userEvent.click(
    screen.getByRole("button", { name: /calculate quote/i }),
  );
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/quote"),
      expect.objectContaining({
        body: expect.stringContaining('"custom_material":'),
      }),
    ),
  );
  const call = fetchMock.mock.calls.find(
    ([url, options]) =>
      String(url).endsWith("/quote") && options?.method === "POST",
  );
  expect(JSON.parse(String(call?.[1]?.body)).items[0]).toEqual(
    expect.objectContaining({
      material: custom.canonical_name,
      custom_material: custom,
      catalogue_surface_id: null,
    }),
  );
});
it("blocks a lost quote-only draft and provides a real Catalogue return link", async () => {
  currentSearch = `custom_material_id=${crypto.randomUUID()}`;
  renderEditor();
  expect(await screen.findByRole("alert")).toHaveTextContent(/no longer has/);
  expect(
    screen.getByRole("link", { name: "Return to the Catalogue" }),
  ).toHaveAttribute("href", "/catalogue");
  expect(
    screen.queryByRole("button", { name: /calculate quote/i }),
  ).not.toBeInTheDocument();
});

function renderEditor() {
  const view = render(<NewQuotePage />);
  const ai = screen.queryByText("Draft with AI (optional)");
  if (ai) fireEvent.click(ai);
  const toggle = screen.queryByLabelText("Show all sections");
  if (toggle) fireEvent.click(toggle);
  return view;
}

it("guides material to layout to details to review without losing measurements", async () => {
  render(<NewQuotePage />);
  expect(
    screen.getByRole("heading", { name: "1. Material & customer" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("combobox", { name: "Worktop layout" }),
  ).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/customer name/i), "Pilot");
  await userEvent.click(screen.getByRole("button", { name: "Next: Layout" }));
  await userEvent.selectOptions(
    screen.getByLabelText("Worktop layout"),
    "l_shape",
  );
  await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
  await userEvent.type(screen.getByLabelText("Piece B length (mm)"), "1800");
  await userEvent.click(
    screen.getByRole("button", { name: "Next: Design details" }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Previous" }));
  expect(screen.getByLabelText("Piece B length (mm)")).toHaveValue(1800);
});

it("records sink details and prices measured upstands as a separate line", async () => {
  renderEditor();
  await userEvent.type(screen.getByLabelText(/customer name/i), "Pilot");
  await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
  await userEvent.click(screen.getByLabelText(/sink \/ hob cutout/i));
  await userEvent.selectOptions(
    screen.getByLabelText("Sink mounting"),
    "Undermount",
  );
  await userEvent.click(screen.getByLabelText(/upstand included/i));
  await userEvent.type(screen.getByLabelText("Upstand length (mm)"), "3000");
  await userEvent.type(screen.getByLabelText("Upstand height (mm)"), "100");
  await userEvent.click(
    screen.getByRole("button", { name: /calculate quote/i }),
  );
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).endsWith("/quote")),
    ).toBe(true),
  );
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/quote"));
  const body = JSON.parse(String(call?.[1]?.body));
  expect(body.items[0].notes).toContain("Undermount");
  expect(body.items[1]).toMatchObject({
    item_type: "upstand",
    length_mm: 3000,
    width_mm: 100,
  });
});

it("saves a drawing through the existing customer-document API and references it in the quote", async () => {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/customers?"))
      return jsonResponse([{ id: "customer-1", name: "Pilot" }]);
    if (url.includes("/documents?"))
      return jsonResponse(
        { id: "drawing-1", original_filename: "kitchen.pdf" },
        201,
      );
    if (url.endsWith("/quote"))
      return jsonResponse({
        id: "quote-1",
        customer: "Pilot",
        items: [],
        total: 100,
        price_before_vat: 83.33,
        vat: 16.67,
      });
    return jsonResponse([]);
  });
  renderEditor();
  await waitFor(() =>
    expect(
      screen.getByLabelText(/link to existing customer/i),
    ).toBeInTheDocument(),
  );
  await userEvent.selectOptions(
    screen.getByLabelText(/link to existing customer/i),
    "customer-1",
  );
  await userEvent.type(screen.getByLabelText(/^length \(mm\)$/i), "2400");
  await userEvent.upload(
    screen.getByLabelText("Upload layout drawing (optional)"),
    new File(["%PDF-1.4"], "kitchen.pdf", { type: "application/pdf" }),
  );
  await waitFor(() =>
    expect(screen.getByText(/Saved drawing: kitchen.pdf/)).toBeInTheDocument(),
  );
  await userEvent.click(
    screen.getByRole("button", { name: /calculate quote/i }),
  );
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([u]) => String(u).endsWith("/quote")),
    ).toBe(true),
  );
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/quote"));
  expect(JSON.parse(String(call?.[1]?.body)).items[0].notes).toContain(
    "drawing-1",
  );
});
