/**
 * Sprint 025 — Business Command Centre frontend contract
 * (docs/SPRINTS/sprint-025.md §3): real API response shape → rendered
 * sections, loading/error/empty states, never a fabricated fallback
 * value.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearToken, setToken } from "@/lib/auth-storage";

import { CommandCentrePanel } from "./CommandCentrePanel";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const FULL_STATS = {
  customers: 4,
  pipeline: {
    enquiry: 2,
    quoted: 1,
    booked: 1,
    templated: 0,
    fabricated: 0,
    installed: 0,
    complete: 0,
  },
  quotes: { draft: 1, approved: 2, handed_off: 1 },
  value: { quoted_value: 12500, approved_quoted_value: 9000 },
  site_visits: { scheduled: 2, completed: 1, cancelled: 0 },
  follow_up: { unread_follow_ups: 3 },
};

const EMPTY_STATS = {
  customers: 0,
  pipeline: {
    enquiry: 0,
    quoted: 0,
    booked: 0,
    templated: 0,
    fabricated: 0,
    installed: 0,
    complete: 0,
  },
  quotes: { draft: 0, approved: 0, handed_off: 0 },
  value: { quoted_value: 0, approved_quoted_value: 0 },
  site_visits: { scheduled: 0, completed: 0, cancelled: 0 },
  follow_up: { unread_follow_ups: 0 },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setToken("pytest-owner-token");
});

afterEach(() => {
  cleanup();
  clearToken();
  vi.unstubAllGlobals();
});

describe("CommandCentrePanel — business command centre (Sprint 025)", () => {
  it("renders_real_metrics_from_the_command_centre_endpoint", async () => {
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/dashboard/command-centre")) {
        return jsonResponse(FULL_STATS);
      }
      throw new Error(`Unexpected fetch in test: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CommandCentrePanel />);

    await waitFor(() => {
      expect(screen.getByText("Business Command Centre")).toBeInTheDocument();
    });

    expect(screen.getByText("Enquiry")).toBeInTheDocument();
    expect(screen.getByText("Handed off")).toBeInTheDocument();
    expect(screen.getByText("Quoted value")).toBeInTheDocument();
    expect(screen.getByText("£12,500")).toBeInTheDocument();
    expect(screen.getByText("3 unread")).toBeInTheDocument();
  });

  it("renders_zeros_not_a_blank_or_broken_state_for_an_empty_tenant", async () => {
    fetchMock = vi.fn(async () => jsonResponse(EMPTY_STATS));
    vi.stubGlobal("fetch", fetchMock);

    render(<CommandCentrePanel />);

    await waitFor(() => {
      expect(screen.getByText("Business Command Centre")).toBeInTheDocument();
    });

    // Real zeros, not a fabricated non-zero fallback and not an error banner.
    expect(screen.queryByText(/couldn.t load/i)).not.toBeInTheDocument();
    expect(screen.getByText("Unread follow-ups")).toBeInTheDocument();
    expect(screen.queryByText(/unread$/)).not.toBeInTheDocument(); // no badge when 0
  });

  it("shows_a_real_error_state_on_api_failure_never_a_fabricated_zero", async () => {
    fetchMock = vi.fn(async () => jsonResponse({ detail: "boom" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    render(<CommandCentrePanel />);

    await waitFor(() => {
      expect(screen.getByText(/couldn.t load the business command centre/i)).toBeInTheDocument();
    });

    // No stale/fabricated metric text ever renders on a failed load.
    expect(screen.queryByText("Business Command Centre")).not.toBeInTheDocument();
  });
});
