export type NotificationType = "success" | "warning" | "info" | "error";

// Sprint 024 (docs/SPRINTS/sprint-024.md) — source_type is a closed set of
// known entity kinds this app knows how to navigate to; source_id is that
// entity's id. Both null for every notification created before this
// sprint (tenant-wide broadcasts) and for any future notification with
// nothing safe to link to.
export type NotificationSourceType = "project";

export interface AppNotification {
  id: string;
  title: string;
  message: string;
  type: NotificationType;
  timestamp: string;
  read: boolean;
  source_type: NotificationSourceType | null;
  source_id: string | null;
}

/**
 * Notification preferences (Sprint 039, Workstream B) — mirrors
 * app/notifications/models.py's `NotificationPreferenceOut`.
 *
 * `label` and `description` are served alongside the flags rather than
 * hardcoded in the settings screen, so the UI can never offer a switch
 * for a category GeoCore does not actually produce — the same
 * served-vocabulary rule as /automations/meta and /projects/meta/pipeline.
 */
export interface NotificationPreference {
  category: string;
  label: string;
  description: string;
  /** The bell menu. On by default for every category, which is exactly
   * what the Sprint 036 localStorage card defaulted to. */
  in_app: boolean;
  /** A real email. Off by default for every category — turning it on is
   * always a deliberate act, never an upgrade's side effect. */
  email: boolean;
}

export interface NotificationPreferenceUpdate {
  category: string;
  in_app: boolean;
  email: boolean;
}
