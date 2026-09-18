// GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — mirrors
// app/workflows/models.py. WorkflowRole is the same 13-value stable
// semantic-role vocabulary the backend's dashboard/automations/AI all read
// (Task 7); this is the frontend's one copy of it.

export const WORKFLOW_ROLES = [
  "lead",
  "survey",
  "quoted",
  "approved",
  "procurement",
  "scheduled",
  "in_progress",
  "inspection",
  "snagging",
  "handover",
  "completed",
  "on_hold",
  "cancelled",
] as const;

export type WorkflowRole = (typeof WORKFLOW_ROLES)[number];

export const WORKFLOW_ROLE_LABELS: Record<WorkflowRole, string> = {
  lead: "Lead",
  survey: "Survey",
  quoted: "Quoted",
  approved: "Approved",
  procurement: "Procurement",
  scheduled: "Scheduled",
  in_progress: "In Progress",
  inspection: "Inspection",
  snagging: "Snagging",
  handover: "Handover",
  completed: "Completed",
  on_hold: "On Hold",
  cancelled: "Cancelled",
};

export const WORKFLOW_ROLE_TONE: Record<
  WorkflowRole,
  "neutral" | "info" | "warning" | "success" | "danger" | "accent"
> = {
  lead: "neutral",
  survey: "info",
  quoted: "info",
  approved: "accent",
  procurement: "warning",
  scheduled: "warning",
  in_progress: "warning",
  inspection: "warning",
  snagging: "warning",
  handover: "warning",
  completed: "success",
  on_hold: "neutral",
  cancelled: "danger",
};

/** The workflow-facing part of a Project (ProjectOut.workflow) — present
 * on every project regardless of trade, alongside the still-unchanged
 * legacy `status` field. */
export interface ProjectWorkflowSummary {
  template_key: string;
  template_name: string;
  stage_key: string;
  stage_label: string;
  role: WorkflowRole;
}

export interface GateBlocker {
  code: string;
  message: string;
}

export interface WorkflowTransitionOption {
  stage_key: string;
  stage_label: string;
  role: WorkflowRole;
  blocked_requirements: GateBlocker[];
}

export interface ProjectWorkflowDetail extends ProjectWorkflowSummary {
  is_terminal: boolean;
  allowed_transitions: WorkflowTransitionOption[];
}

export interface WorkflowHistoryEntry {
  id: string;
  from_stage_key: string | null;
  from_stage_label: string | null;
  to_stage_key: string;
  to_stage_label: string;
  actor_user_id: string | null;
  reason: string | null;
  created_at: string;
}
