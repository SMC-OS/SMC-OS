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
