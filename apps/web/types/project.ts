export const PROJECT_STATUSES = [
  "enquiry",
  "quoted",
  "booked",
  "templated",
  "fabricated",
  "installed",
  "complete",
] as const;

export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export interface ProjectCreate {
  name: string;
  customer_id?: string | null;
  notes?: string | null;
}

export interface Project extends ProjectCreate {
  id: string;
  quote_id: string | null;
  status: ProjectStatus;
  created_at: string;
  // Sprint 023 (docs/SPRINTS/sprint-023.md) — the responsible Staff/Owner
  // member, if any.
  assigned_user_id: string | null;
}
