/**
 * Sprint 036 (Workstream E) — the general construction quote builder.
 *
 * This is the sprint's central product claim, so the tests are about the
 * claim rather than the widgets: a bathroom refit can be priced, the
 * arithmetic on screen is the arithmetic that gets saved, and no slab
 * data is invented for a job that has none.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const createGeneralQuoteMock = vi.fn();
const updateGeneralQuoteMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getCustomers: () =>
        Promise.resolve([
          {
            id: "customer-1",
            name: "Ada Okafor",
            company_name: null,
            customer_type: "individual",
            address_line1: "14 Elm Road",
            address_line2: null,
            city: "Manchester",
            postcode: "M1 4BT",
            created_at: new Date().toISOString(),
          },
        ]),
      getTrades: () =>
        Promise.resolve([
          { key: "bathroom", label: "Bathrooms", default_quote_kind: "general" },
          { key: "stone", label: "Stone & Worktops", default_quote_kind: "stone" },
        ]),
      getQuoteUnits: () =>
        Promise.resolve([
          { key: "item", label: "item" },
          { key: "day", label: "day" },
        ]),
      createGeneralQuote: (...args: unknown[]) => createGeneralQuoteMock(...args),
      updateGeneralQuote: (...args: unknown[]) => updateGeneralQuoteMock(...args),
    },
  };
});

vi.mock("@/components/workspace/WorkspaceProvider", () => ({
  useWorkspace: () => ({
    profile: null,
    currency: "GBP",
    loading: false,
    refresh: () => {},
  }),
}));

import { GeneralQuoteBuilder } from "./GeneralQuoteBuilder";

beforeEach(() => {
  createGeneralQuoteMock.mockReset();
  updateGeneralQuoteMock.mockReset();
});

afterEach(() => {
  cleanup();
});

async function fillFirstLine(description: string, quantity: string, rate: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Description"), description);

  const quantityField = screen.getByLabelText("Quantity");
  await user.clear(quantityField);
  await user.type(quantityField, quantity);

  const rateField = screen.getByLabelText("Rate (£)");
  await user.clear(rateField);
  await user.type(rateField, rate);
}

describe("GeneralQuoteBuilder — Sprint 036", () => {
  it("prices work that has nothing to do with stone", async () => {
    const user = userEvent.setup();
    createGeneralQuoteMock.mockResolvedValue({
      id: "quote-1",
      title: "Bathroom refit",
      currency: "GBP",
      total: 960,
      vat: 160,
    });

    render(<GeneralQuoteBuilder />);
    await waitFor(() => {
      expect(screen.getByLabelText("Type of work")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Quote title"), "Bathroom refit");
    await fillFirstLine("Strip out existing bathroom", "2.5", "320");
    await user.click(screen.getByRole("button", { name: /create quote/i }));

    await waitFor(() => {
      expect(createGeneralQuoteMock).toHaveBeenCalled();
    });

    const payload = createGeneralQuoteMock.mock.calls[0][0];
    expect(payload.title).toBe("Bathroom refit");
    expect(payload.lines).toHaveLength(1);
    expect(payload.lines[0]).toMatchObject({
      description: "Strip out existing bathroom",
      quantity: 2.5,
      unit_price: 320,
    });
    // The whole point: nothing slab-shaped is sent for a job that has no
    // slabs.
    expect(payload).not.toHaveProperty("material");
    expect(payload).not.toHaveProperty("length_mm");
  });

  it("shows a running total that matches what will be saved", async () => {
    render(<GeneralQuoteBuilder />);
    await waitFor(() => {
      expect(screen.getByLabelText("Quantity")).toBeInTheDocument();
    });

    await fillFirstLine("Labour", "2.5", "320");

    // 2.5 x 320 = 800, +20% VAT = 960. Each line is rounded to 2dp and
    // then summed, exactly as the backend does — computing it the other
    // way round produces a total the line items do not add up to.
    await waitFor(() => {
      expect(screen.getAllByText("£960.00").length).toBeGreaterThan(0);
    });
    // £800.00 appears twice by design — once on the line and once as the
    // subtotal — which is itself the property under test: the line total
    // and the subtotal are the same number.
    expect(screen.getAllByText("£800.00")).toHaveLength(2);
  });

  it("adds and removes line items", async () => {
    const user = userEvent.setup();
    render(<GeneralQuoteBuilder />);
    await waitFor(() => {
      expect(screen.getByLabelText("Description")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /add line/i }));
    await waitFor(() => {
      expect(screen.getAllByLabelText("Description")).toHaveLength(2);
    });

    await user.click(screen.getByRole("button", { name: "Remove line 2" }));
    await waitFor(() => {
      expect(screen.getAllByLabelText("Description")).toHaveLength(1);
    });
  });

  it("keeps the last line — a quote with no lines has no price", async () => {
    render(<GeneralQuoteBuilder />);
    await waitFor(() => {
      expect(screen.getByLabelText("Description")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: "Remove line 1" })).not.toBeInTheDocument();
  });

  it("prefills the site address from the chosen customer", async () => {
    const user = userEvent.setup();
    render(<GeneralQuoteBuilder />);
    await waitFor(() => {
      expect(screen.getByLabelText("Customer")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText("Customer"), "customer-1");

    await waitFor(() => {
      expect(screen.getByLabelText("Address line 1")).toHaveValue("14 Elm Road");
    });
    expect(screen.getByLabelText("Town or city")).toHaveValue("Manchester");
  });

  it("shows a discount line only once there is a discount", async () => {
    const user = userEvent.setup();
    render(<GeneralQuoteBuilder />);
    await waitFor(() => {
      expect(screen.getByLabelText("Discount (£)")).toBeInTheDocument();
    });

    expect(screen.queryByText("Discount")).not.toBeInTheDocument();

    await fillFirstLine("Labour", "1", "1000");
    await user.type(screen.getByLabelText("Discount (£)"), "100");

    await waitFor(() => {
      expect(screen.getByText("Discount")).toBeInTheDocument();
    });
    // 1000 - 100 = 900, +20% = 1080.
    expect(screen.getAllByText("£1,080.00").length).toBeGreaterThan(0);
  });
});

// Sprint 039 Production Readiness Defect Gate, Blocker 5 — the builder
// already priced work correctly; it just had no way to open an existing
// draft back up and change it. `updateGeneralQuote` existed in the API
// client and the backend's PATCH /quotes/{id} was already fully built and
// tested — nothing in the UI ever called it.
function makeExistingQuote(overrides: Record<string, unknown> = {}) {
  return {
    id: "quote-42",
    customer_id: "customer-1",
    quote_kind: "general",
    title: "Bathroom refit, 14 Elm Road",
    trade: "bathroom",
    site_address_line1: "14 Elm Road",
    site_address_line2: null,
    site_city: "Manchester",
    site_postcode: "M1 4BT",
    scope_of_works: "Strip out and refit.",
    notes: "Customer wants tiles supplied separately.",
    exclusions: "Decoration excluded.",
    terms: "50% up front.",
    valid_until: "2026-12-01",
    currency: "GBP",
    vat_rate: 0.2,
    subtotal: 800,
    discount_amount: 50,
    sent_at: null,
    material: null,
    thickness: null,
    kitchen_length: null,
    island: false,
    waterfall: 0,
    splashback: false,
    upstands: false,
    postcode: "M1 4BT",
    price_per_slab: 0,
    price_before_vat: 750,
    vat: 150,
    total: 900,
    items: [
      {
        id: "item-1",
        position: 0,
        item_type: "other",
        line_kind: "labour",
        description: "Strip out existing bathroom",
        unit: "day",
        unit_price: 320,
        material: null,
        thickness: null,
        quantity: 2.5,
        length_mm: null,
        width_mm: null,
        thickness_mm: null,
        unit_input: "mm",
        notes: null,
        price_per_slab: null,
        slabs: null,
        line_total: 800,
      },
    ],
    status: "draft",
    approved_at: null,
    approved_by_user_id: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("GeneralQuoteBuilder — editing an existing draft (Sprint 039 Blocker 5)", () => {
  it("prefills every field from the quote being edited", async () => {
    // @ts-expect-error — the fixture is a plain object shaped like Quote,
    // not imported as the type, to keep this test file's own mocked
    // shapes self-contained.
    render(<GeneralQuoteBuilder existingQuote={makeExistingQuote()} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Quote title")).toHaveValue(
        "Bathroom refit, 14 Elm Road"
      );
    });
    expect(screen.getByLabelText("Address line 1")).toHaveValue("14 Elm Road");
    expect(screen.getByLabelText("Town or city")).toHaveValue("Manchester");
    expect(screen.getByLabelText("Postcode")).toHaveValue("M1 4BT");
    expect(screen.getByLabelText("Description")).toHaveValue(
      "Strip out existing bathroom"
    );
    expect(screen.getByLabelText("Quantity")).toHaveValue(2.5);
    expect(screen.getByLabelText("Rate (£)")).toHaveValue(320);
    expect(screen.getByLabelText("Discount (£)")).toHaveValue(50);
    expect(screen.getByLabelText("Exclusions")).toHaveValue("Decoration excluded.");
  });

  it("saves changes to the existing quote instead of creating a new one", async () => {
    const user = userEvent.setup();
    updateGeneralQuoteMock.mockResolvedValue({
      ...makeExistingQuote(),
      title: "Bathroom refit, updated",
    });

    // @ts-expect-error — see note above.
    render(<GeneralQuoteBuilder existingQuote={makeExistingQuote()} />);
    await waitFor(() => {
      expect(screen.getByLabelText("Quote title")).toHaveValue(
        "Bathroom refit, 14 Elm Road"
      );
    });

    const titleField = screen.getByLabelText("Quote title");
    await user.clear(titleField);
    await user.type(titleField, "Bathroom refit, updated");

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(updateGeneralQuoteMock).toHaveBeenCalled();
    });
    expect(createGeneralQuoteMock).not.toHaveBeenCalled();

    const [id, payload] = updateGeneralQuoteMock.mock.calls[0];
    expect(id).toBe("quote-42");
    expect(payload.title).toBe("Bathroom refit, updated");

    expect(await screen.findByText(/quote updated/i)).toBeInTheDocument();
  });
});
