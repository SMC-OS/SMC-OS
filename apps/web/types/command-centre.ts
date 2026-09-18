export interface PipelineCounts {
  enquiry: number;
  quoted: number;
  booked: number;
  templated: number;
  fabricated: number;
  installed: number;
  complete: number;
}

/** GeoCore Premium OS Plan 01 (Sprint 040, Task 7/9) — the semantic,
 * trade-adaptive sibling of PipelineCounts above: one field per
 * WorkflowRole, always all 13 present and 0 if none (mirrors
 * app/dashboard/models.py's PipelineRoleCounts). Never replaces
 * `pipeline` on CommandCentreStats below — an addition, same dual-field
 * pattern as every other Plan 01 rollout surface. */
export interface PipelineRoleCounts {
  lead: number;
  survey: number;
  quoted: number;
  approved: number;
  procurement: number;
  scheduled: number;
  in_progress: number;
  inspection: number;
  snagging: number;
  handover: number;
  completed: number;
  on_hold: number;
  cancelled: number;
}

export interface QuoteFunnel {
  draft: number;
  approved: number;
  handed_off: number;
}

export interface QuotedValue {
  quoted_value: number;
  approved_quoted_value: number;
}

export interface SiteVisitCounts {
  scheduled: number;
  completed: number;
  cancelled: number;
}

export interface FollowUpAttention {
  unread_follow_ups: number;
}

/** GeoCore Premium OS Plan 04 (Sprint 043), Task 20 — scoped to projects
 * that actually have a base contract (a linked, handed-off quote); an
 * enquiry with no quote yet has nothing meaningful to report. Never a
 * company-wide margin percentage — only honest counts, since some
 * projects' cost data may be incomplete. */
export interface FinancialSignals {
  approved_contract_value: number;
  approved_variations_value: number;
  projects_with_margin_risk: number;
  projects_with_missing_cost_data: number;
  projects_with_a_contract: number;
}

export interface CommandCentreStats {
  customers: number;
  pipeline: PipelineCounts;
  pipeline_by_role: PipelineRoleCounts;
  quotes: QuoteFunnel;
  value: QuotedValue;
  site_visits: SiteVisitCounts;
  follow_up: FollowUpAttention;
  financials: FinancialSignals;
}
