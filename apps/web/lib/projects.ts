import type { ProjectStatus } from "@/types/project";

/** Display label + Badge tone per pipeline stage (Sprint 006) — same
 * per-type mapping convention as lib/activity.ts's ACTIVITY_ICON/TONE. */

export const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = {
  enquiry: "Enquiry",
  quoted: "Quoted",
  booked: "Booked",
  templated: "Templated",
  fabricated: "Fabricated",
  installed: "Installed",
  complete: "Complete",
};

export const PROJECT_STATUS_TONE: Record<
  ProjectStatus,
  "neutral" | "info" | "warning" | "success"
> = {
  enquiry: "neutral",
  quoted: "info",
  booked: "info",
  templated: "warning",
  fabricated: "warning",
  installed: "warning",
  complete: "success",
};
