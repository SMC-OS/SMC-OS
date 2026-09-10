import type { PipelineRole } from "@/types/project";

/**
 * Sprint 039 (Workstream D, §4 Decision 3) re-keyed this from the seven
 * stone-named stages to the eight trade-neutral roles. A stone tenant's
 * `templated`, `fabricated` and `installed` jobs all count as
 * `in_progress`, so this reads correctly for a roofing business and a
 * worktop fabricator at the same time.
 *
 * Keyed by PipelineRole rather than listed field-by-field so adding a
 * role to the shared vocabulary cannot leave this type behind.
 */
export type PipelineCounts = Record<PipelineRole, number>;

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

export interface CommandCentreStats {
  customers: number;
  pipeline: PipelineCounts;
  quotes: QuoteFunnel;
  value: QuotedValue;
  site_visits: SiteVisitCounts;
  follow_up: FollowUpAttention;
}
