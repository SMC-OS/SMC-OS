import type { PipelineRole, PipelineStage } from "@/types/project";

/**
 * Display treatment for a pipeline stage (Sprint 039, Workstream D).
 *
 * Sprint 006 mapped each of seven fixed statuses to a label and a Badge
 * tone. Neither can be a fixed map any more: a stage's *label* is tenant
 * configuration served alongside the stage, and the set of stage keys
 * differs between businesses.
 *
 * What every tenant still shares is the stage's role, so that is what the
 * tone keys off — a job in progress looks the same whether this business
 * calls that stage `fabricated` or `in_progress`. Same per-type mapping
 * convention as lib/activity.ts's ACTIVITY_ICON/TONE.
 */

export type BadgeTone = "neutral" | "info" | "warning" | "success" | "danger";

export const PIPELINE_ROLE_TONE: Record<PipelineRole, BadgeTone> = {
  lead: "neutral",
  quoted: "info",
  approved: "info",
  scheduled: "info",
  in_progress: "warning",
  on_hold: "neutral",
  completed: "success",
  cancelled: "danger",
};

/**
 * Fallback wording for a role, for the places that count jobs by role
 * rather than by stage — the dashboard pipeline column, for instance.
 * Wherever a real stage record is to hand, prefer its own `label`: that
 * is the word this business chose.
 */
export const PIPELINE_ROLE_LABEL: Record<PipelineRole, string> = {
  lead: "Planning",
  quoted: "Quoted",
  approved: "Approved",
  scheduled: "Scheduled",
  in_progress: "In progress",
  on_hold: "On hold",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function stageTone(role: PipelineRole | null | undefined): BadgeTone {
  return role ? PIPELINE_ROLE_TONE[role] ?? "neutral" : "neutral";
}

/**
 * What to call a project's current stage.
 *
 * Falls back to the raw stage key rather than to a generic placeholder: a
 * project sitting on a stage its tenant has since reconfigured away should
 * still show what the record actually says, not "Unknown".
 */
export function stageLabel(
  stages: PipelineStage[] | null | undefined,
  statusKey: string
): string {
  return stages?.find((stage) => stage.key === statusKey)?.label ?? statusKey;
}

/** Find a stage record by key. */
export function findStage(
  stages: PipelineStage[] | null | undefined,
  statusKey: string
): PipelineStage | undefined {
  return stages?.find((stage) => stage.key === statusKey);
}

/**
 * The moves this project may make right now, in pipeline order.
 *
 * Read straight from the stage's own `allowed_transitions` rather than
 * re-derived here, so this UI cannot offer a transition the backend will
 * refuse.
 */
export function nextStages(
  stages: PipelineStage[] | null | undefined,
  statusKey: string
): PipelineStage[] {
  const current = findStage(stages, statusKey);
  if (!current || !stages) return [];
  return current.allowed_transitions
    .map((key) => stages.find((stage) => stage.key === key))
    .filter((stage): stage is PipelineStage => Boolean(stage));
}
