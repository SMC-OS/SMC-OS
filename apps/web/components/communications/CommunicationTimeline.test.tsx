/**
 * Communication history UI contract (Sprint 039, Workstream A).
 *
 * The three things this screen exists to get right, and which a
 * well-meaning refactor could quietly break:
 *
 *   1. "Sent" is never presented as "arrived".
 *   2. A spam complaint is shown *alongside* the delivery status, never
 *      instead of it (sprint-039.md §4 Decision 1).
 *   3. A failure says what happened and what to do, and offers retry only
 *      where the backend said retry applies.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import { CommunicationTimeline } from "./CommunicationTimeline";

function makeCommunication(overrides: Record<string, unknown> = {}) {
  return {
    id: "comm-1",
    tenant_id: "tenant-1",
    customer_id: "customer-1",
    quote_id: null,
    project_id: null,
    invitation_id: null,
    automation_id: null,
    automation_run_id: null,
    channel: "email",
    direction: "outbound",
    message_type: "quote_sent",
    recipient: "jane@example.com",
    subject: "Your quote from Pytest Co",
    status: "sent",
    attempt_count: 1,
    last_attempted_at: new Date().toISOString(),
    failure_category: null,
    failure_detail: null,
    complained: false,
    retryable: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;
let currentRows: Record<string, unknown>[] = [];

beforeEach(() => {
  currentRows = [makeCommunication()];
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.includes("/communications/") && init?.method === "POST") {
      return jsonResponse(
        makeCommunication({ status: "sent", retryable: false, attempt_count: 2 })
      );
    }
    if (url.includes("/communications")) {
      return jsonResponse(currentRows);
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

describe("CommunicationTimeline — Sprint 039", () => {
  it("shows_who_it_went_to_what_it_was_and_its_delivery_state", async () => {
    render(<CommunicationTimeline />);

    expect(await screen.findByText("Your quote from Pytest Co")).toBeInTheDocument();
    expect(screen.getByText(/jane@example\.com/)).toBeInTheDocument();
    expect(screen.getByText("Sent")).toBeInTheDocument();
  });

  it("never_presents_an_accepted_send_as_a_confirmed_delivery", async () => {
    render(<CommunicationTimeline />);

    await screen.findByText("Sent");

    expect(screen.queryByText("Delivered")).not.toBeInTheDocument();
    // And it says plainly what "Sent" does and does not mean.
    expect(screen.getByText(/not confirmed as arrived/i)).toBeInTheDocument();
  });

  it("shows_delivered_only_when_the_provider_confirmed_it", async () => {
    currentRows = [makeCommunication({ status: "delivered" })];
    render(<CommunicationTimeline />);

    expect(await screen.findByText("Delivered")).toBeInTheDocument();
  });

  it("shows_a_spam_complaint_alongside_the_delivery_status_not_instead_of_it", async () => {
    // §4 Decision 1: a complaint proves the message reached the inbox, so
    // the row must still say it was delivered.
    currentRows = [makeCommunication({ status: "delivered", complained: true })];
    render(<CommunicationTimeline />);

    expect(await screen.findByText("Delivered")).toBeInTheDocument();
    expect(screen.getByText("Marked as spam")).toBeInTheDocument();
  });

  it("explains_a_failure_and_offers_a_retry_when_the_backend_says_it_applies", async () => {
    currentRows = [
      makeCommunication({
        status: "failed",
        failure_category: "transient",
        failure_detail: "The mail provider was briefly unreachable.",
        retryable: true,
      }),
    ];
    render(<CommunicationTimeline />);

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/temporary problem at the mail provider/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("never_offers_a_retry_the_backend_said_does_not_apply", async () => {
    currentRows = [
      makeCommunication({
        status: "bounced",
        failure_category: "permanent",
        retryable: false,
      }),
    ];
    render(<CommunicationTimeline />);

    await screen.findByText("Bounced");

    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });

  it("applies_the_servers_returned_row_after_a_retry_never_an_optimistic_sent", async () => {
    currentRows = [
      makeCommunication({
        status: "failed",
        failure_category: "transient",
        retryable: true,
      }),
    ];
    render(<CommunicationTimeline />);

    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/communications/comm-1/retry"),
        expect.objectContaining({ method: "POST" })
      );
    });
    expect(await screen.findByText("Sent")).toBeInTheDocument();
  });

  it("shows_a_real_empty_state_rather_than_an_empty_panel", async () => {
    currentRows = [];
    render(<CommunicationTimeline emptyTitle="Nothing sent yet" />);

    expect(await screen.findByText("Nothing sent yet")).toBeInTheDocument();
  });

  it("shows_a_real_error_state_when_history_cannot_be_loaded", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: "boom" }, 500));
    render(<CommunicationTimeline />);

    expect(
      await screen.findByText(/couldn.t load communication history/i)
    ).toBeInTheDocument();
  });
});
