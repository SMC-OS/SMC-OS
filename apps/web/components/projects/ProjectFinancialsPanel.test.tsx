/**
 * GeoCore Premium OS Plan 04 (Sprint 043), Task 28 — component coverage
 * for the Project 360 Financials tab: contract/cost/profitability
 * summary rendering, the partial-cost-data warning, the cost table, and
 * the add/delete cost flow. Never a fabricated figure — an unknown base
 * contract or profitability must render as "Unknown", not a guessed 0.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProjectCostEntry, ProjectFinancialSummary } from "@/types/financials";

const getProjectFinancialSummaryMock = vi.fn();
const getProjectCostsMock = vi.fn();
const createProjectCostMock = vi.fn();
const deleteProjectCostMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      getProjectFinancialSummary: (...args: unknown[]) => getProjectFinancialSummaryMock(...args),
      getProjectCosts: (...args: unknown[]) => getProjectCostsMock(...args),
      createProjectCost: (...args: unknown[]) => createProjectCostMock(...args),
      deleteProjectCost: (...args: unknown[]) => deleteProjectCostMock(...args),
    },
  };
});

import { ProjectFinancialsPanel } from "./ProjectFinancialsPanel";

function summary(overrides: Partial<ProjectFinancialSummary> = {}): ProjectFinancialSummary {
  return {
    project_id: "project-1",
    contract: {
      base_contract_value: 20000,
      base_contract_source: "approved_quote",
      approved_variations_total: 4000,
      current_contract_value: 24000,
    },
    costs: {
      budgeted_cost: 0,
      committed_cost: 0,
      actual_cost: 20000,
      forecast_cost: 20000,
      cost_data_status: "partial",
      cost_entry_count: 1,
    },
    profitability: {
      forecast_gross_profit: 4000,
      forecast_gross_margin_percent: 16.67,
      actual_gross_profit: 4000,
      actual_gross_margin_percent: 16.67,
      margin_risk: false,
    },
    ...overrides,
  };
}

function costEntry(overrides: Partial<ProjectCostEntry> = {}): ProjectCostEntry {
  return {
    id: "cost-1",
    project_id: "project-1",
    category: "labour",
    state: "actual",
    description: "Fitting labour",
    supplier_or_payee: null,
    reference: null,
    quantity: null,
    unit: null,
    unit_cost: null,
    total_cost: 20000,
    cost_date: null,
    due_date: null,
    created_by_user_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProjectFinancialsPanel", () => {
  it("renders_contract_cost_and_profitability_summaries_from_real_data", async () => {
    getProjectFinancialSummaryMock.mockResolvedValue(summary());
    getProjectCostsMock.mockResolvedValue([costEntry()]);

    render(<ProjectFinancialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("Contract Summary")).toBeInTheDocument();
    });

    expect(screen.getAllByText("£20,000").length).toBeGreaterThan(0);
    expect(screen.getByText("£24,000")).toBeInTheDocument();
    expect(screen.getByText("Current contract value")).toBeInTheDocument();
    expect(screen.getByText("Forecast cost")).toBeInTheDocument();
    expect(screen.getByText("Fitting labour")).toBeInTheDocument();
    expect(screen.getByText("Partial cost data")).toBeInTheDocument();
  });

  it("never_fabricates_a_base_contract_value_when_none_is_known", async () => {
    getProjectFinancialSummaryMock.mockResolvedValue(
      summary({
        contract: {
          base_contract_value: null,
          base_contract_source: null,
          approved_variations_total: 0,
          current_contract_value: null,
        },
        profitability: {
          forecast_gross_profit: null,
          forecast_gross_margin_percent: null,
          actual_gross_profit: null,
          actual_gross_margin_percent: null,
          margin_risk: false,
        },
      })
    );
    getProjectCostsMock.mockResolvedValue([]);

    render(<ProjectFinancialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("Contract Summary")).toBeInTheDocument();
    });

    expect(screen.getByText("Unknown — no approved quote linked")).toBeInTheDocument();
    expect(screen.getByText("No costs recorded yet")).toBeInTheDocument();
    // Every "Unknown" figure — never a guessed £0.
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
  });

  it("shows_a_margin_risk_badge_when_the_backend_flags_it", async () => {
    getProjectFinancialSummaryMock.mockResolvedValue(
      summary({
        profitability: {
          forecast_gross_profit: 1000,
          forecast_gross_margin_percent: 4.2,
          actual_gross_profit: 1000,
          actual_gross_margin_percent: 4.2,
          margin_risk: true,
        },
      })
    );
    getProjectCostsMock.mockResolvedValue([costEntry()]);

    render(<ProjectFinancialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("Margin risk")).toBeInTheDocument();
    });
  });

  it("adds_a_cost_entry_and_refreshes_the_summary", async () => {
    getProjectFinancialSummaryMock.mockResolvedValue(summary({ costs: { ...summary().costs, cost_entry_count: 0 } }));
    getProjectCostsMock.mockResolvedValue([]);
    createProjectCostMock.mockResolvedValue(costEntry({ id: "cost-2", description: "New worktop" }));

    render(<ProjectFinancialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("No costs recorded yet")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /add cost/i }));
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "New worktop" },
    });
    fireEvent.change(screen.getByLabelText("Total cost"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: /save cost/i }));

    await waitFor(() => {
      expect(createProjectCostMock).toHaveBeenCalledWith(
        "project-1",
        expect.objectContaining({ description: "New worktop", total_cost: 500 })
      );
    });
    expect(await screen.findByText("New worktop")).toBeInTheDocument();
  });

  it("deletes_a_cost_entry", async () => {
    getProjectFinancialSummaryMock.mockResolvedValue(summary());
    getProjectCostsMock.mockResolvedValue([costEntry()]);
    deleteProjectCostMock.mockResolvedValue(undefined);

    render(<ProjectFinancialsPanel projectId="project-1" />);

    await waitFor(() => {
      expect(screen.getByText("Fitting labour")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /delete cost/i }));

    await waitFor(() => {
      expect(deleteProjectCostMock).toHaveBeenCalledWith("project-1", "cost-1");
    });
    await waitFor(() => {
      expect(screen.queryByText("Fitting labour")).not.toBeInTheDocument();
    });
  });
});
