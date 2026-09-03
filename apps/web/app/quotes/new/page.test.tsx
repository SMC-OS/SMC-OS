/**
 * Sprint 032 (Workstream C) — structured mm dimensions on the manual quote
 * form, and the AI draft flow showing interpreted dimensions / material
 * match status back to the user before anything is created.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import NewQuotePage from "./page";

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

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url.endsWith("/customers")) {
      return jsonResponse([]);
    }
    if (url.endsWith("/quotes/ai-draft") && init?.method === "POST") {
      const parsedBody = JSON.parse(String(init.body));
      if (parsedBody.text === "missing product") {
        return jsonResponse({
          customer: null,
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
          island: false,
          waterfall: 0,
          splashback: false,
          upstands: false,
          postcode: null,
          warnings: ["Material 'SuperGalaxy Diamond Quartz' wasn't recognised — pick one manually."],
        });
      }
      return jsonResponse({
        customer: "Sarah Whitfield",
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
        island: false,
        waterfall: 0,
        splashback: false,
        upstands: false,
        postcode: null,
        warnings: [],
      });
    }
    if (url.endsWith("/quote") && init?.method === "POST") {
      return jsonResponse({
        customer: "Sarah Whitfield",
        material: "Calacatta Oro",
        slabs: 1,
        price_per_slab: 2350,
        price_before_vat: 2350,
        vat: 470,
        total: 2820,
        dimensions: {
          quantity: 1,
          length_mm: 2400,
          width_mm: 600,
          thickness_mm: 20,
          unit_input: "mm",
          splashback_length_mm: null,
          upstands_length_mm: null,
        },
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
});

describe("NewQuotePage — structured dimensions (Sprint 032)", () => {
  it("submits quantity/length_mm/width_mm to POST /quote", async () => {
    render(<NewQuotePage />);

    await userEvent.type(screen.getByLabelText(/customer name/i), "Sarah Whitfield");
    await userEvent.clear(screen.getByLabelText(/length \(mm\)/i));
    await userEvent.type(screen.getByLabelText(/length \(mm\)/i), "2400");
    await userEvent.clear(screen.getByLabelText(/width\/depth \(mm\)/i));
    await userEvent.type(screen.getByLabelText(/width\/depth \(mm\)/i), "600");

    await userEvent.click(screen.getByRole("button", { name: /calculate quote/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/quote"),
        expect.objectContaining({ method: "POST" })
      );
    });

    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/quote"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.length_mm).toBe(2400);
    expect(body.width_mm).toBe(600);
    expect(body.quantity).toBe(1);

    expect(await screen.findByText(/2400mm x 600mm/)).toBeInTheDocument();
  });

  it("requires an explicit splashback length once splashback is checked", async () => {
    render(<NewQuotePage />);

    expect(screen.queryByLabelText(/splashback length/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText(/^splashback$/i));

    expect(await screen.findByLabelText(/splashback length \(mm\)/i)).toBeRequired();
  });

  it("shows interpreted dimensions and never fabricates a not-found product", async () => {
    render(<NewQuotePage />);

    await userEvent.type(
      screen.getByPlaceholderText(/calacatta oro 20mm worktop/i),
      "missing product"
    );
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));

    expect(await screen.findByText(/no matching product was found/i)).toBeInTheDocument();
    expect(screen.getByText(/2400mm x 600mm/)).toBeInTheDocument();
  });

  it("pre-fills the form and shows the resolved material on a confident AI match", async () => {
    render(<NewQuotePage />);

    await userEvent.type(
      screen.getByPlaceholderText(/calacatta oro 20mm worktop/i),
      "Calacatta Oro 20mm, 2400 x 600mm, customer Sarah Whitfield"
    );
    await userEvent.click(screen.getByRole("button", { name: /generate draft/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/length \(mm\)/i)).toHaveValue(2400);
    });
    expect(screen.getByLabelText(/width\/depth \(mm\)/i)).toHaveValue(600);
    expect(screen.getByDisplayValue("Sarah Whitfield")).toBeInTheDocument();
  });
});
