/** GeoCore Premium OS Plan 04 (Sprint 043) — mirrors app/financials/models.py.
 * The project cost ledger + contract/profitability summaries. Trade-neutral
 * by construction: nothing here assumes stone, a slab or a material. */

export const COST_CATEGORIES = [
  "material",
  "labour",
  "subcontractor",
  "plant",
  "transport",
  "other",
] as const;
export type CostCategory = (typeof COST_CATEGORIES)[number];

export const COST_CATEGORY_LABELS: Record<CostCategory, string> = {
  material: "Material",
  labour: "Labour",
  subcontractor: "Subcontractor",
  plant: "Plant",
  transport: "Transport",
  other: "Other",
};

export const COST_STATES = ["budgeted", "committed", "actual"] as const;
export type CostState = (typeof COST_STATES)[number];

export const COST_STATE_LABELS: Record<CostState, string> = {
  budgeted: "Budgeted",
  committed: "Committed",
  actual: "Actual",
};

export type CostDataStatus = "none" | "partial" | "complete";

export interface ProjectCostEntryIn {
  category: CostCategory;
  state: CostState;
  description: string;
  supplier_or_payee?: string | null;
  reference?: string | null;
  quantity?: number | null;
  unit?: string | null;
  unit_cost?: number | null;
  total_cost: number;
  cost_date?: string | null;
  due_date?: string | null;
}

export type ProjectCostEntryUpdate = Partial<ProjectCostEntryIn>;

export interface ProjectCostEntry {
  id: string;
  project_id: string;
  category: CostCategory;
  state: CostState;
  description: string;
  supplier_or_payee: string | null;
  reference: string | null;
  quantity: number | null;
  unit: string | null;
  unit_cost: number | null;
  total_cost: number;
  cost_date: string | null;
  due_date: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

/** One entry per cost state, 0.0 if none recorded — never a sparse dict. */
export interface CostSummary {
  budgeted_cost: number;
  committed_cost: number;
  actual_cost: number;
  forecast_cost: number;
  cost_data_status: CostDataStatus;
  cost_entry_count: number;
}

/** base_contract_value/current_contract_value are null when there is no
 * safe, non-fabricated source (an approved, handed-off quote) — never a
 * guessed zero. */
export interface ContractSummary {
  base_contract_value: number | null;
  base_contract_source: string | null;
  approved_variations_total: number;
  current_contract_value: number | null;
}

/** null on any figure that would otherwise be fabricated. forecast_* and
 * actual_* are distinct and must never be shown interchangeably. */
export interface ProfitabilitySummary {
  forecast_gross_profit: number | null;
  forecast_gross_margin_percent: number | null;
  actual_gross_profit: number | null;
  actual_gross_margin_percent: number | null;
  margin_risk: boolean;
}

export interface ProjectFinancialSummary {
  project_id: string;
  contract: ContractSummary;
  costs: CostSummary;
  profitability: ProfitabilitySummary;
}
