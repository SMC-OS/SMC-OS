/**
 * Automations (Sprint 036, Workstream G).
 *
 * Everything an automation can do is internal to the workspace. GeoCore
 * has no outbound email, SMS or messaging infrastructure, so nothing here
 * contacts a customer — the `draft_message` action prepares a message and
 * hands it to a person as a task. `AutomationMeta.delivery` carries that
 * fact from the backend so the UI states it rather than assuming it.
 */

export interface AutomationTrigger {
  key: string;
  label: string;
  description: string;
  /** "event" fires immediately; "scan" is evaluated on a schedule. */
  kind: "event" | "scan";
  subject_type: string;
}

export interface AutomationMeta {
  triggers: AutomationTrigger[];
  actions: string[];
  operators: string[];
  delivery: {
    external_delivery_available: boolean;
    note: string;
  };
}

export interface AutomationCondition {
  field: string;
  op: string;
  value: unknown;
}

export interface AutomationAction {
  type: string;
  config: {
    title?: string;
    message?: string;
    body?: string;
    due_in_days?: number;
  };
}

export interface Automation {
  id: string;
  name: string;
  description: string | null;
  template_key: string | null;
  trigger_type: string;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutomationTemplate {
  key: string;
  name: string;
  description: string;
  trigger_type: string;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
}

/** Execution history. A skipped run carries its reason and a failed run
 * carries its message — this is the only place an automation failure is
 * visible, which is why it is a first-class part of the feature. */
export interface AutomationRun {
  id: string;
  automation_id: string;
  trigger_type: string;
  subject_type: string | null;
  subject_id: string | null;
  status: "succeeded" | "failed" | "skipped";
  detail: string | null;
  created_at: string;
}

export interface AutomationCreate {
  name: string;
  description?: string | null;
  trigger_type: string;
  conditions?: AutomationCondition[];
  actions: AutomationAction[];
  enabled?: boolean;
}

export type AutomationUpdate = Partial<AutomationCreate>;

export const ACTION_LABELS: Record<string, string> = {
  create_notification: "Send an in-app notification",
  create_task: "Create a follow-up task",
  draft_message: "Draft a message for you to send",
  create_project_from_quote: "Create the project from the quote",
};
