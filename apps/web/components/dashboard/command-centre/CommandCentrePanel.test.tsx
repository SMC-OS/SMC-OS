/**
 * Sprint 025 — Business Command Centre frontend contract
 * (docs/SPRINTS/sprint-025.md §3): real API response shape → rendered
 * sections, loading/error/empty states, never a fabricated fallback
 * value.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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

// GeoCore Premium OS Plan 01 (Sprint 040, Task 9) — every fixture below
// carries `pipeline_by_role` alongside the unchanged `pipeline`, matching
// CommandCentreResponse's own dual-field shape.
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
  pipeline_by_role: {
    lead: 2,
    survey: 0,
    quoted: 1,
    approved: 0,
    procurement: 0,
    scheduled: 1,
    in_progress: 0,
    inspection: 0,
    snagging: 0,
    handover: 0,
    completed: 0,
    on_hold: 0,
    cancelled: 0,
  },
  quotes: { draft: 1, approved: 2, handed_off: 1 },
  value: { quoted_value: 12500, approved_quoted_value: 9000 },
  site_visits: { scheduled: 2, completed: 1, cancelled: 0 },
  follow_up: { unread_follow_ups: 3 },
  // GeoCore Premium OS Plan 04 (Sprint 043), Task 20.
  financials: {
    approved_contract_value: 48000,
    approved_variations_value: 3250,
    projects_with_margin_risk: 1,
    projects_with_missing_cost_data: 1,
    projects_with_a_contract: 2,
  },
  // GeoCore Premium OS Plan 05 (Sprint 044), Task 25.
  procurement: {
    materials_required: 4,
    purchase_orders_awaiting_approval: 2,
    purchase_orders_ordered: 3,
    late_deliveries: 1,
    materials_due_this_week: 2,
    projects_blocked_by_materials: 1,
  },
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
  pipeline_by_role: {
    lead: 0,
    survey: 0,
    quoted: 0,
    approved: 0,
    procurement: 0,
    scheduled: 0,
    in_progress: 0,
    inspection: 0,
    snagging: 0,
    handover: 0,
    completed: 0,
    on_hold: 0,
    cancelled: 0,
  },
  quotes: { draft: 0, approved: 0, handed_off: 0 },
  value: { quoted_value: 0, approved_quoted_value: 0 },
  site_visits: { scheduled: 0, completed: 0, cancelled: 0 },
  follow_up: { unread_follow_ups: 0 },
  financials: {
    approved_contract_value: 0,
    approved_variations_value: 0,
    projects_with_margin_risk: 0,
    projects_with_missing_cost_data: 0,
    projects_with_a_contract: 0,
  },
  procurement: {
    materials_required: 0,
    purchase_orders_awaiting_approval: 0,
    purchase_orders_ordered: 0,
    late_deliveries: 0,
    materials_due_this_week: 0,
    projects_blocked_by_materials: 0,
  },
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

    // GeoCore Premium OS Plan 01 (Sprint 040, Task 9) — the Pipeline card
    // now renders the 13 shared semantic roles, not the old 7-value
    // stone-shaped status pipeline.
    expect(screen.getByText("Lead")).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Handed off")).toBeInTheDocument();
    expect(screen.getByText("Quoted value")).toBeInTheDocument();
    expect(screen.getByText("£12,500")).toBeInTheDocument();
    expect(screen.getByText("3 unread")).toBeInTheDocument();

    // GeoCore Premium OS Plan 04 (Sprint 043), Task 20 — real financial
    // signals, precisely labelled (never "quote value" for a contract
    // value, never a fabricated company-wide margin).
    expect(screen.getByText("Contract & Margin")).toBeInTheDocument();
    expect(screen.getByText("Approved contract value")).toBeInTheDocument();
    expect(screen.getByText("£48,000")).toBeInTheDocument();
    expect(screen.getByText("Approved variations value")).toBeInTheDocument();
    expect(screen.getByText("£3,250")).toBeInTheDocument();
    expect(screen.getByText("Projects with missing cost data")).toBeInTheDocument();
    expect(screen.getByText("1 margin risk")).toBeInTheDocument();

    // GeoCore Premium OS Plan 05 (Sprint 044), Task 25 — real procurement
    // signals, never meaningless metric clutter.
    expect(screen.getByRole("heading", { name: "Procurement" })).toBeInTheDocument();
    expect(screen.getByText("Materials required")).toBeInTheDocument();
    expect(screen.getByText("Purchase orders awaiting approval")).toBeInTheDocument();
    expect(screen.getByText("Projects blocked by materials")).toBeInTheDocument();
    expect(screen.getByText("1 late")).toBeInTheDocument();
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

    // No margin-risk badge when the tenant has no projects with a contract
    // (the CountRow label "Projects with margin risk" still renders — only
    // the numbered badge, e.g. "1 margin risk", is conditional).
    expect(screen.getByText("Contract & Margin")).toBeInTheDocument();
    expect(screen.queryByText(/^\d+ margin risk$/)).not.toBeInTheDocument();

    // No late-delivery badge when nothing is late.
    expect(screen.getByRole("heading", { name: "Procurement" })).toBeInTheDocument();
    expect(screen.queryByText(/^\d+ late$/)).not.toBeInTheDocument();
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

  it("reports_an_expired_session_distinctly_from_a_real_api_outage", async () => {
    // Production incident (post-v1.0.1): a 401 (expired/invalid token) was
    // shown identically to a real 5xx outage — "Couldn't load the Business
    // Command Centre" for both. A 401 is a session problem, not an API
    // availability problem.
    fetchMock = vi.fn(async () => jsonResponse({ detail: "Could not validate credentials" }, 401));
    vi.stubGlobal("fetch", fetchMock);

    render(<CommandCentrePanel />);

    await waitFor(() => {
      expect(screen.queryByText(/couldn.t load the business command centre/i)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/session/i)).toBeInTheDocument();
  });

  it("renders_every_semantic_role_even_when_zero_never_a_sparse_pipeline", async () => {
    // GeoCore Premium OS Plan 01 (Sprint 040, Task 9) — all 13 roles
    // always render, 0 if none, same never-sparse contract the old
    // 7-value pipeline had.
    fetchMock = vi.fn(async () => jsonResponse(EMPTY_STATS));
    vi.stubGlobal("fetch", fetchMock);

    render(<CommandCentrePanel />);

    await waitFor(() => {
      expect(screen.getByText("Business Command Centre")).toBeInTheDocument();
    });

    const pipelineCard = screen.getByText("Pipeline").closest(".rounded-2xl") as HTMLElement;
    for (const label of [
      "Lead",
      "Survey",
      "Quoted",
      "Approved",
      "Procurement",
      "Scheduled",
      "In Progress",
      "Inspection",
      "Snagging",
      "Handover",
      "Completed",
      "On Hold",
      "Cancelled",
    ]) {
      expect(within(pipelineCard).getByText(label)).toBeInTheDocument();
    }
  });
});
