export const TASK_STATUSES = ["open", "done", "cancelled"] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

/**
 * Sprint 036 — a piece of internal work someone needs to do. One shape
 * serving the project task list, the automation engine's output, the
 * dashboard attention list and the calendar.
 *
 * `body` carries a prepared message for the `draft_message` automation
 * action — a human reads it and sends it themselves. GeoCore has no
 * channel to send it through.
 */
export interface Task {
  id: string;
  title: string;
  body: string | null;
  status: TaskStatus;
  due_at: string | null;
  assigned_user_id: string | null;
  source_type: string | null;
  source_id: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface TaskCreate {
  title: string;
  body?: string | null;
  due_at?: string | null;
  assigned_user_id?: string | null;
  source_type?: string | null;
  source_id?: string | null;
}
