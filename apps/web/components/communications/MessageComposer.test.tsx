/**
 * The human review gate (Sprint 039, Workstream C).
 *
 * This component is where "AI must never silently send" is actually
 * enforced in the product. The tests that matter most are the ones that
 * would fail if someone added a convenient "draft and send" shortcut.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import { MessageComposer } from "./MessageComposer";

const CUSTOMER_ID = "customer-1";

const DRAFT = {
  kind: "general",
  subject: "About your kitchen",
  body: "Hi Jane,\n\nThe scaffolding goes up on Monday.",
  engine: "llm",
  grounded_in: ["Customer: Jane Okafor"],
};

const COMMUNICATION = {
  id: "comm-1",
  tenant_id: "tenant-1",
  customer_id: CUSTOMER_ID,
  quote_id: null,
  project_id: null,
  invitation_id: null,
  automation_id: null,
  automation_run_id: null,
  channel: "email",
  direction: "outbound",
  message_type: "customer_message",
  recipient: "jane@example.com",
  subject: "About your kitchen",
  status: "sent",
  attempt_count: 1,
  last_attempted_at: new Date().toISOString(),
  failure_category: null,
  failure_detail: null,
  complained: false,
  retryable: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    if (url.endsWith("/ai/draft") || url.endsWith("/ai/rewrite")) {
      return jsonResponse(DRAFT);
    }
    if (url.endsWith("/communications/send")) {
      return jsonResponse(COMMUNICATION);
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

function sendCalls() {
  return fetchMock.mock.calls.filter(([input]) =>
    String(input).endsWith("/communications/send")
  );
}

describe("MessageComposer — the human review gate", () => {
  it("drafting_writes_into_the_fields_and_sends_nothing", async () => {
    // The single most important assertion in this file.
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable />);

    await userEvent.click(screen.getByRole("button", { name: /draft with geocore ai/i }));

    await waitFor(() =>
      expect(screen.getByLabelText(/subject/i)).toHaveValue("About your kitchen")
    );
    expect(sendCalls()).toHaveLength(0);
  });

  it("shows_what_the_draft_was_grounded_in_so_it_can_be_judged", async () => {
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable />);

    await userEvent.click(screen.getByRole("button", { name: /draft with geocore ai/i }));

    expect(await screen.findByText(/Customer: Jane Okafor/)).toBeInTheDocument();
  });

  it("sends_only_when_a_person_presses_send", async () => {
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable />);

    await userEvent.type(screen.getByLabelText(/subject/i), "Hello");
    await userEvent.type(screen.getByLabelText(/message/i), "A message.");
    expect(sendCalls()).toHaveLength(0);

    await userEvent.click(screen.getByRole("button", { name: /send to customer/i }));

    await waitFor(() => expect(sendCalls()).toHaveLength(1));
  });

  it("sends_exactly_what_is_on_screen_including_the_reviewers_edits", async () => {
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable />);

    await userEvent.click(screen.getByRole("button", { name: /draft with geocore ai/i }));
    await waitFor(() =>
      expect(screen.getByLabelText(/subject/i)).toHaveValue("About your kitchen")
    );
    await userEvent.clear(screen.getByLabelText(/subject/i));
    await userEvent.type(screen.getByLabelText(/subject/i), "My own subject");
    await userEvent.click(screen.getByRole("button", { name: /send to customer/i }));

    await waitFor(() => expect(sendCalls()).toHaveLength(1));
    const body = JSON.parse(sendCalls()[0][1].body as string);
    expect(body.subject).toBe("My own subject");
  });

  it("cannot_send_an_empty_message", async () => {
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable />);

    expect(screen.getByRole("button", { name: /send to customer/i })).toBeDisabled();
  });

  it("lets_someone_write_and_send_without_touching_the_ai", async () => {
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable={false} />);

    expect(
      screen.queryByRole("button", { name: /draft with geocore ai/i })
    ).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/subject/i), "Hello");
    await userEvent.type(screen.getByLabelText(/message/i), "A message.");
    await userEvent.click(screen.getByRole("button", { name: /send to customer/i }));

    await waitFor(() => expect(sendCalls()).toHaveLength(1));
  });

  it("hides_drafting_entirely_when_no_provider_is_connected", () => {
    // Hidden, not disabled: a greyed-out button that always fails teaches
    // nothing about why.
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable={false} />);

    expect(
      screen.queryByRole("button", { name: /draft with geocore ai/i })
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/tone/i)).not.toBeInTheDocument();
  });

  it("reports_the_real_outcome_rather_than_a_cheerful_confirmation", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/communications/send")) {
        return jsonResponse({
          ...COMMUNICATION,
          status: "failed",
          failure_category: "unavailable",
          failure_detail: "No email provider is configured.",
        });
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable={false} />);

    await userEvent.type(screen.getByLabelText(/subject/i), "Hello");
    await userEvent.type(screen.getByLabelText(/message/i), "A message.");
    await userEvent.click(screen.getByRole("button", { name: /send to customer/i }));

    expect(await screen.findByText("Not sent")).toBeInTheDocument();
    expect(screen.getByText(/no email provider is configured/i)).toBeInTheDocument();
  });

  it("explains_a_missing_email_address_rather_than_failing_silently", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ detail: "This customer has no email address on file." }, 422)
    );
    render(<MessageComposer customerId={CUSTOMER_ID} draftingAvailable={false} />);

    await userEvent.type(screen.getByLabelText(/subject/i), "Hello");
    await userEvent.type(screen.getByLabelText(/message/i), "A message.");
    await userEvent.click(screen.getByRole("button", { name: /send to customer/i }));

    expect(
      await screen.findByText(/no email address on file/i)
    ).toBeInTheDocument();
  });
});
