/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 5 — the edit page
 * fetches the quote and either renders the builder pre-filled, or refuses
 * plainly for the same three reasons the backend PATCH does: not found,
 * not a general quote, or not a draft.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import EditQuotePage from "./page";

const QUOTE_ID = "quote-1";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: QUOTE_ID }),
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
}));

let authRole = "Owner";
vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isReady: true,
    role: authRole,
  }),
}));

vi.mock("@/components/workspace/WorkspaceProvider", () => ({
  useWorkspace: () => ({ currency: "GBP" }),
}));

function makeQuote(overrides: Record<string, unknown> = {}) {
  return {
    id: QUOTE_ID,
    customer_id: null,
    quote_kind: "general",
    title: "Bathroom refit",
    trade: "bathroom",
    site_address_line1: null,
    site_address_line2: null,
    site_city: null,
    site_postcode: null,
    scope_of_works: null,
    notes: null,
    exclusions: null,
    terms: null,
    valid_until: null,
    currency: "GBP",
    vat_rate: 0.2,
    subtotal: 800,
    discount_amount: null,
    sent_at: null,
    material: null,
    thickness: null,
    kitchen_length: null,
    island: false,
    waterfall: 0,
    splashback: false,
    upstands: false,
    postcode: null,
    price_per_slab: 0,
    price_before_vat: 800,
    vat: 160,
    total: 960,
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

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;
let quoteResponse: ReturnType<typeof makeQuote>;

beforeEach(() => {
  authRole = "Owner";
  quoteResponse = makeQuote();
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith(`/quotes/${QUOTE_ID}`)) return jsonResponse(quoteResponse);
    if (url.endsWith("/customers?limit=200")) return jsonResponse([]);
    if (url.endsWith("/quotes/meta/trades")) return jsonResponse([]);
    if (url.endsWith("/quotes/meta/units")) return jsonResponse([{ key: "day", label: "day" }]);
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
});

afterEach(() => {
  cleanup();
  clearToken();
  vi.unstubAllGlobals();
});

describe("EditQuotePage", () => {
  it("renders the builder pre-filled for a draft general quote", async () => {
    render(<EditQuotePage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Quote title")).toHaveValue("Bathroom refit");
    });
    expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();
  });

  it("refuses plainly for a stone quote instead of rendering a form that would fail", async () => {
    quoteResponse = makeQuote({ quote_kind: "stone" });
    render(<EditQuotePage />);

    expect(await screen.findByText(/stone quotes use their own template/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Quote title")).not.toBeInTheDocument();
  });

  it("refuses plainly for a quote that has already been sent", async () => {
    quoteResponse = makeQuote({ status: "sent" });
    render(<EditQuotePage />);

    expect(
      await screen.findByText(/already been sent or approved/i)
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Quote title")).not.toBeInTheDocument();
  });

  it("also lets a Staff user edit — the backend allows Owner and Staff alike", async () => {
    authRole = "Staff";
    render(<EditQuotePage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Quote title")).toHaveValue("Bathroom refit");
    });
  });
});
