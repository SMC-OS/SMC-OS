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
  status: ProjectStatus;
  created_at: string;
}
