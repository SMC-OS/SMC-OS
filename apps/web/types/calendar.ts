/**
 * The operational calendar (Sprint 036, Workstream K).
 *
 * Every item is a real row the workspace already owns. Nothing is
 * predicted or synthesised, and there is no external calendar
 * integration — GeoCore does not sync with Google or Microsoft, and the
 * UI does not imply that it does.
 */
export const CALENDAR_ITEM_TYPES = [
  "project_start",
  "project_target_completion",
  "site_visit",
  "task_due",
  "quote_expiry",
] as const;

export type CalendarItemType = (typeof CALENDAR_ITEM_TYPES)[number];

export interface CalendarItem {
  id: string;
  type: CalendarItemType;
  title: string;
  subtitle: string | null;
  /** ISO date for an all-day item, ISO datetime otherwise. */
  at: string;
  /** Project dates and quote expiries are genuinely all-day; rendering
   * them at an arbitrary hour is the classic calendar bug this prevents. */
  all_day: boolean;
  source_type: string;
  source_id: string;
  status: string | null;
}

export interface CalendarResponse {
  /** The window actually served — the API clamps an over-long request
   * rather than refusing it, so the client renders what it got. */
  start: string;
  end: string;
  items: CalendarItem[];
}
