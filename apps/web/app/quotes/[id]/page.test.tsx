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
const PROJECT_ID = "project-1";

// Hoisted so a test can assert on the exact call — a factory returning a
// fresh vi.fn() per useRouter() call would give each render its own spy,
// making "was push called with X" unobservable from the test.
const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: QUOTE_ID }),
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
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

function makeProject(overrides: Record<string, unknown> = {}) {
  return {
    id: PROJECT_ID,
    quote_id: QUOTE_ID,
    customer_id: null,
    name: `Quote ${QUOTE_ID}`,
    notes: null,
    status: "booked",
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
    if (url.endsWith(`/quotes/${QUOTE_ID}/handoff`) && init?.method === "POST") {
      return jsonResponse(makeProject());
    }
    if (url.endsWith(`/quotes/${QUOTE_ID}`)) {
      return jsonResponse(makeQuote({ status: currentStatus }));
    }
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
  pushMock.mockClear();
  replaceMock.mockClear();
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

  it("lets an Owner/Staff user hand off an approved quote and opens the returned project", async () => {
    currentStatus = "approved";
    render(<QuoteDetailPage />);

    const handoffButton = await screen.findByRole("button", {
      name: /hand off to project/i,
    });
    expect(handoffButton).toBeInTheDocument();

    await userEvent.click(handoffButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/quotes/${QUOTE_ID}/handoff`),
        expect.objectContaining({ method: "POST" })
      );
    });

    // The server response is authoritative — the destination must be the
    // returned Project's own id, never derived from the Quote id.
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith(`/projects/${PROJECT_ID}`);
    });
  });
});
