/**
 * Sprint 021 — frontend enquiry-to-customer conversion contract (mirrors
 * the backend's convert_to_customer() behavior,
 * tests/test_enquiry_conversion.py). Structural twin of
 * app/quotes/[id]/page.test.tsx (Sprint 020's quote-handoff frontend
 * contract).
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import ProjectDetailPage from "./page";

const PROJECT_ID = "project-1";
const CUSTOMER_ID = "customer-1";

// Hoisted so a test can assert on the exact call — same reasoning as
// app/quotes/[id]/page.test.tsx.
const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT_ID }),
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

function makeProject(overrides: Record<string, unknown> = {}) {
  return {
    id: PROJECT_ID,
    quote_id: null,
    customer_id: null,
    name: "Riverside Kitchen Enquiry",
    notes: null,
    status: "enquiry",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function makeCustomer(overrides: Record<string, unknown> = {}) {
  return {
    id: CUSTOMER_ID,
    name: "Jane Okafor",
    email: "jane@example.com",
    phone: "07123 456789",
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

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (
      url.endsWith(`/projects/${PROJECT_ID}/convert-to-customer`) &&
      init?.method === "POST"
    ) {
      return jsonResponse(makeCustomer());
    }
    if (url.endsWith(`/projects/${PROJECT_ID}`)) {
      return jsonResponse(makeProject());
    }
    throw new Error(`Unexpected fetch in test: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("pytest-owner-token");
  pushMock.mockClear();
  replaceMock.mockClear();
});

afterEach(() => {
  cleanup();
  clearToken();
  vi.unstubAllGlobals();
});

describe("ProjectDetailPage — enquiry conversion (Sprint 021)", () => {
  it("lets_owner_or_staff_convert_an_unlinked_enquiry_into_a_customer", async () => {
    render(<ProjectDetailPage />);

    const convertButton = await screen.findByRole("button", {
      name: /convert to customer/i,
    });
    expect(convertButton).toBeInTheDocument();

    await userEvent.click(convertButton);

    await userEvent.type(await screen.findByLabelText(/full name/i), "Jane Okafor");
    await userEvent.type(screen.getByLabelText(/email/i), "jane@example.com");
    await userEvent.type(screen.getByLabelText(/phone/i), "07123 456789");

    await userEvent.click(screen.getByRole("button", { name: /save customer/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/projects/${PROJECT_ID}/convert-to-customer`),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            name: "Jane Okafor",
            email: "jane@example.com",
            phone: "07123 456789",
          }),
        })
      );
    });

    // The server's returned Customer is authoritative.
    expect(await screen.findByText("Jane Okafor")).toBeInTheDocument();

    // Conversion is a one-time action against an unlinked enquiry — once
    // linked, there is nothing left to convert.
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /convert to customer/i })
      ).not.toBeInTheDocument();
    });
  });

  it("keeps_enquiry_unlinked_and_retryable_when_customer_conversion_fails", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();

      if (
        url.endsWith(`/projects/${PROJECT_ID}/convert-to-customer`) &&
        init?.method === "POST"
      ) {
        return jsonResponse({ detail: "Conversion failed" }, 500);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}`)) {
        return jsonResponse(makeProject());
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });

    render(<ProjectDetailPage />);

    const convertButton = await screen.findByRole("button", {
      name: /convert to customer/i,
    });
    await userEvent.click(convertButton);

    await userEvent.type(await screen.findByLabelText(/full name/i), "Jane Okafor");
    await userEvent.type(screen.getByLabelText(/email/i), "jane@example.com");
    await userEvent.type(screen.getByLabelText(/phone/i), "07123 456789");

    await userEvent.click(screen.getByRole("button", { name: /save customer/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/projects/${PROJECT_ID}/convert-to-customer`),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            name: "Jane Okafor",
            email: "jane@example.com",
            phone: "07123 456789",
          }),
        })
      );
    });

    // A failed conversion must never attach a Customer — no linked-customer
    // presentation and no rendering of the typed/returned name as fact.
    expect(screen.queryByRole("link", { name: /jane okafor/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Jane Okafor")).not.toBeInTheDocument();

    // The existing error card renders the failure, no new toast/modal
    // system — same convention as
    // keeps_the_user_on_the_quote_and_restores_handoff_after_api_failure
    // (app/quotes/[id]/page.test.tsx).
    expect(await screen.findByText(/failed with 500/i)).toBeInTheDocument();

    // The form must remain available, still holding the user's input, and
    // re-enabled so they can retry without re-entering everything.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save customer/i })).toBeEnabled();
    });
    expect(screen.getByLabelText(/full name/i)).toHaveValue("Jane Okafor");
  });
});
