/**
 * Sprint 020 — frontend quote-approval contract (mirrors the backend's
 * approve() behavior, tests/test_quote_handoff.py). First component-level
 * test in the repo — see vitest.config.ts's docstring for why.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import QuoteDetailPage from "./page";

const QUOTE_ID = "quote-1";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: QUOTE_ID }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
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

function makeQuote(overrides: Record<string, unknown> = {}) {
  return {
    id: QUOTE_ID,
    customer_id: null,
    material: "Calacatta Gold",
    thickness: "20mm",
    kitchen_length: 3,
    island: false,
    waterfall: 0,
    splashback: false,
    upstands: false,
    postcode: null,
    price_per_slab: 100,
    price_before_vat: 1000,
    vat: 200,
    total: 1200,
    status: "draft",
    approved_at: null,
    approved_by_user_id: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

let currentStatus: string;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  currentStatus = "draft";
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url.endsWith(`/quotes/${QUOTE_ID}/approve`) && init?.method === "POST") {
      currentStatus = "approved";
      return jsonResponse(
        makeQuote({ status: "approved", approved_at: new Date().toISOString() })
      );
    }
    if (url.endsWith(`/quotes/${QUOTE_ID}`)) {
      return jsonResponse(makeQuote({ status: currentStatus }));
    }
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
});

afterEach(() => {
  clearToken();
  vi.unstubAllGlobals();
});

describe("QuoteDetailPage — approval (Sprint 020)", () => {
  it("lets an Owner/Staff user approve a draft quote and updates the rendered status", async () => {
    render(<QuoteDetailPage />);

    const approveButton = await screen.findByRole("button", { name: /approve/i });
    expect(approveButton).toBeInTheDocument();

    await userEvent.click(approveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/quotes/${QUOTE_ID}/approve`),
        expect.objectContaining({ method: "POST" })
      );
    });

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    });
    expect(await screen.findByText(/approved/i)).toBeInTheDocument();
  });
});
