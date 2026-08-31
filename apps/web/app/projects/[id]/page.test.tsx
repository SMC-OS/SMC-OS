/**
 * Sprint 021 — frontend enquiry-to-customer conversion contract (mirrors
 * the backend's convert_to_customer() behavior,
 * tests/test_enquiry_conversion.py). Structural twin of
 * app/quotes/[id]/page.test.tsx (Sprint 020's quote-handoff frontend
 * contract).
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import ProjectDetailPage from "./page";

const PROJECT_ID = "project-1";
const CUSTOMER_ID = "customer-1";
const APPOINTMENT_ID = "appointment-1";

// Hoisted so a test can assert on the exact call — same reasoning as
// app/quotes/[id]/page.test.tsx.
const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: PROJECT_ID }),
  useRouter: () => ({ replace: replaceMock, push: pushMock }),
}));

// Mutable so individual tests can exercise a different role without a
// second mock setup — same reasoning as fetchMock's currentProjectOverrides
// below (a nested closure inside a hoisted vi.mock factory reads whatever
// the variable holds at call time, not at mock-registration time).
let currentRole: string | null = "Owner";

vi.mock("@/components/auth/AuthProvider", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isReady: true,
    tenantName: "Pytest Co",
    role: currentRole,
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

function makeAppointment(overrides: Record<string, unknown> = {}) {
  return {
    id: APPOINTMENT_ID,
    tenant_id: "tenant-1",
    project_id: PROJECT_ID,
    created_by_user_id: "owner-1",
    scheduled_at: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
    status: "scheduled",
    notes: null,
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
// Mutable per-test Project fixture overrides (status/customer_id) — read by
// the default fetchMock's GET handler below, same mutable-fixture pattern
// as currentRole above.
let currentProjectOverrides: Record<string, unknown> = {};
// Mutable per-test Appointment list fixture — read by the default
// fetchMock's GET /appointments handler below.
let currentAppointments: Record<string, unknown>[] = [];

beforeEach(() => {
  currentRole = "Owner";
  currentProjectOverrides = {};
  currentAppointments = [];
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (
      url.endsWith(`/projects/${PROJECT_ID}/convert-to-customer`) &&
      init?.method === "POST"
    ) {
      return jsonResponse(makeCustomer());
    }
    if (
      url.endsWith(`/projects/${PROJECT_ID}/appointments`) &&
      init?.method === "POST"
    ) {
      return jsonResponse(makeAppointment());
    }
    if (url.endsWith(`/projects/${PROJECT_ID}/appointments`)) {
      return jsonResponse(currentAppointments);
    }
    if (
      url.endsWith(`/appointments/${APPOINTMENT_ID}/status`) &&
      init?.method === "PATCH"
    ) {
      const body = JSON.parse(init.body as string) as { status: string };
      return jsonResponse(makeAppointment({ status: body.status }));
    }
    if (url.endsWith(`/projects/${PROJECT_ID}`)) {
      return jsonResponse(makeProject(currentProjectOverrides));
    }
    if (url.endsWith(`/customers/${CUSTOMER_ID}`)) {
      return jsonResponse(makeCustomer());
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

  it("shows_convert_to_customer_for_staff_on_unlinked_enquiry", async () => {
    currentRole = "Staff";
    render(<ProjectDetailPage />);

    expect(
      await screen.findByRole("button", { name: /convert to customer/i })
    ).toBeInTheDocument();
  });

  it("hides_convert_to_customer_from_user_without_owner_or_staff_role", async () => {
    currentRole = null;
    render(<ProjectDetailPage />);

    // Wait for the project to actually finish loading before asserting
    // absence, so "not rendered yet" can't masquerade as correct gating.
    await screen.findByText("Riverside Kitchen Enquiry");

    expect(
      screen.queryByRole("button", { name: /convert to customer/i })
    ).not.toBeInTheDocument();
  });

  it("hides_convert_to_customer_for_non_enquiry_project", async () => {
    currentProjectOverrides = { status: "booked" };
    render(<ProjectDetailPage />);

    await screen.findByText("Riverside Kitchen Enquiry");

    expect(
      screen.queryByRole("button", { name: /convert to customer/i })
    ).not.toBeInTheDocument();
  });

  it("hides_convert_to_customer_when_project_already_has_customer", async () => {
    currentProjectOverrides = { customer_id: CUSTOMER_ID };
    render(<ProjectDetailPage />);

    expect(await screen.findByRole("link", { name: /jane okafor/i })).toBeInTheDocument();

    expect(
      screen.queryByRole("button", { name: /convert to customer/i })
    ).not.toBeInTheDocument();
  });
});

describe("ProjectDetailPage — site visit scheduling (Sprint 022)", () => {
  it("lets_owner_or_staff_schedule_a_site_visit", async () => {
    render(<ProjectDetailPage />);

    const scheduleButton = await screen.findByRole("button", {
      name: /schedule site visit/i,
    });
    await userEvent.click(scheduleButton);

    const dateInput = screen.getByLabelText(/date & time/i);
    fireEvent.change(dateInput, { target: { value: "2030-01-01T10:00" } });
    await userEvent.type(screen.getByLabelText(/notes/i), "Measure kitchen worktop");

    await userEvent.click(screen.getByRole("button", { name: /save site visit/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/projects/${PROJECT_ID}/appointments`),
        expect.objectContaining({ method: "POST" })
      );
    });

    // The server's returned Appointment is authoritative — applied only
    // after a successful response, never optimistically.
    expect(await screen.findByText("scheduled")).toBeInTheDocument();

    // Scheduling closes the form back to the trigger button, ready for the
    // next site visit.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /schedule site visit/i })
      ).toBeInTheDocument();
    });
  });

  it("keeps_the_form_and_shows_an_error_when_scheduling_fails", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();

      if (
        url.endsWith(`/projects/${PROJECT_ID}/appointments`) &&
        init?.method === "POST"
      ) {
        return jsonResponse({ detail: "Scheduling failed" }, 500);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/appointments`)) {
        return jsonResponse([]);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}`)) {
        return jsonResponse(makeProject());
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });

    render(<ProjectDetailPage />);

    await userEvent.click(
      await screen.findByRole("button", { name: /schedule site visit/i })
    );
    fireEvent.change(screen.getByLabelText(/date & time/i), {
      target: { value: "2030-01-01T10:00" },
    });

    await userEvent.click(screen.getByRole("button", { name: /save site visit/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/projects/${PROJECT_ID}/appointments`),
        expect.objectContaining({ method: "POST" })
      );
    });

    // A failed schedule attempt must never render a phantom appointment.
    expect(screen.queryByText("scheduled")).not.toBeInTheDocument();

    expect(await screen.findByText(/failed with 500/i)).toBeInTheDocument();

    // The form remains open, still holding the user's input, re-enabled
    // for a retry.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save site visit/i })).toBeEnabled();
    });
    expect(screen.getByLabelText(/date & time/i)).toHaveValue("2030-01-01T10:00");
  });

  it("shows_schedule_site_visit_for_staff", async () => {
    currentRole = "Staff";
    render(<ProjectDetailPage />);

    expect(
      await screen.findByRole("button", { name: /schedule site visit/i })
    ).toBeInTheDocument();
  });

  it("hides_site_visits_section_from_user_without_owner_or_staff_role", async () => {
    currentRole = null;
    render(<ProjectDetailPage />);

    await screen.findByText("Riverside Kitchen Enquiry");

    expect(screen.queryByText(/site visits/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /schedule site visit/i })
    ).not.toBeInTheDocument();
  });

  it("lets_owner_complete_a_scheduled_site_visit", async () => {
    currentAppointments = [makeAppointment()];
    render(<ProjectDetailPage />);

    const completeButton = await screen.findByRole("button", { name: /^complete$/i });
    await userEvent.click(completeButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/appointments/${APPOINTMENT_ID}/status`),
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ status: "completed" }),
        })
      );
    });

    expect(await screen.findByText("completed")).toBeInTheDocument();

    // A terminal appointment has no further transition actions.
    expect(screen.queryByRole("button", { name: /^complete$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
  });

  it("keeps_the_appointment_scheduled_and_shows_an_error_when_completing_fails", async () => {
    currentAppointments = [makeAppointment()];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();

      if (
        url.endsWith(`/appointments/${APPOINTMENT_ID}/status`) &&
        init?.method === "PATCH"
      ) {
        return jsonResponse({ detail: "Transition failed" }, 500);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/appointments`)) {
        return jsonResponse(currentAppointments);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}`)) {
        return jsonResponse(makeProject());
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });

    render(<ProjectDetailPage />);

    const completeButton = await screen.findByRole("button", { name: /^complete$/i });
    await userEvent.click(completeButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/appointments/${APPOINTMENT_ID}/status`),
        expect.objectContaining({ method: "PATCH" })
      );
    });

    // A failed transition must never advance the displayed status.
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
    expect(await screen.findByText("scheduled")).toBeInTheDocument();
    expect(await screen.findByText(/failed with 500/i)).toBeInTheDocument();

    // The action remains available for a retry.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^complete$/i })).toBeEnabled();
    });
  });
});
