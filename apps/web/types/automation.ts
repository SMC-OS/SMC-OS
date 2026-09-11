/**
 * Automations (Sprint 036, Workstream G; corrected Sprint 039,
 * Workstream E).
 *
 * The header here used to say "GeoCore has no outbound email, SMS or
 * messaging infrastructure, so nothing here contacts a customer". That
 * stopped being true when Sprint 038 shipped `send_quote_follow_up`, and
 * this file did not notice: `ACTION_LABELS` below had four entries for
 * five action types, so the one action that *does* email a customer
 * rendered with no label at all.
 *
 * The fix is to stop describing actions here. `AutomationMeta.action_catalogue`
 * carries each action's label, description and class from the backend, so
 * the builder cannot fall out of step with the engine again.
 */

export interface AutomationTrigger {
  key: string;
  label: string;
  description: string;
  /** "event" fires immediately; "scan" is evaluated on a schedule. */
  kind: "event" | "scan";
  subject_type: string;
}

/** The four classes of thing an automation can do. The one that matters
 * most is `customer_communication`: it reaches a real customer's inbox. */
export type ActionKind =
  | "internal_notification"
  | "internal_task"
  | "customer_communication"
  | "ai_draft";

export interface AutomationActionSpec {
  key: string;
  label: string;
  description: string;
  kind: ActionKind;
}

export interface AutomationMeta {
  triggers: AutomationTrigger[];
  actions: string[];
  /** Sprint 038. Kept as-is; Sprint 039 derives it from the catalogue
   * server-side so the two cannot disagree. */
  customer_facing_actions: string[];
  /** Sprint 039 — what each action is, in the words to show a user. */
  action_catalogue: AutomationActionSpec[];
  action_kinds: ActionKind[];
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

/**
 * How each class of action is described to a user, and how it is
 * coloured. This is the one thing the frontend still owns, because it is
 * presentation rather than capability — the actions themselves come from
 * `AutomationMeta.action_catalogue`.
 */
export const ACTION_KIND_LABEL: Record<ActionKind, string> = {
  internal_notification: "Notifies your team",
  internal_task: "Creates work in your workspace",
  customer_communication: "Emails your customer",
  ai_draft: "GeoCore AI drafts it for you",
};

export const ACTION_KIND_TONE: Record<
  ActionKind,
  "neutral" | "info" | "warning" | "accent"
> = {
  internal_notification: "neutral",
  internal_task: "neutral",
  // Deliberately the loudest tone on the screen. This is the one class of
  // action whose mistakes land in someone else's inbox.
  customer_communication: "warning",
  ai_draft: "accent",
};

/** Fall back to the stored key rather than to "Unknown" for an action a
 * newer backend knows about and this build does not — a reader is better
 * served by the raw name than by a shrug. */
export function actionLabel(
  catalogue: AutomationActionSpec[] | undefined,
  type: string
): string {
  return catalogue?.find((entry) => entry.key === type)?.label ?? type;
}

export function actionKind(
  catalogue: AutomationActionSpec[] | undefined,
  type: string
): ActionKind | null {
  return catalogue?.find((entry) => entry.key === type)?.kind ?? null;
}
