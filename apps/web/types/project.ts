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

/**
 * Sprint 036 note, recorded here because this is where a reader meets it:
 * "templated" and "fabricated" are stone-industry stages and make no
 * sense for a roofing or decorating job. Renaming the pipeline to
 * something trade-neutral is real work — it touches the status column,
 * the linear-transition rules, every existing project's history and the
 * dashboard — and it is deliberately deferred rather than half-done here.
 * See docs/SPRINTS/sprint-036.md §10.
 */
export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  enquiry: "Enquiry",
  quoted: "Quoted",
  booked: "Booked",
  templated: "Templated",
  fabricated: "Fabricated",
  installed: "Installed",
  complete: "Complete",
};

export interface ProjectCreate {
  name: string;
  customer_id?: string | null;
  notes?: string | null;
  // Sprint 036 (Workstream F). `project_type` shares its vocabulary with
  // a quote's `trade`, so an approved quote hands its trade straight to
  // the project it becomes.
  project_type?: string | null;
  description?: string | null;
  site_address_line1?: string | null;
  site_address_line2?: string | null;
  site_city?: string | null;
  site_postcode?: string | null;
  start_date?: string | null;
  target_completion_date?: string | null;
  estimated_value?: number | null;
}

/** PATCH body. Status is deliberately absent — it has its own endpoint
 * with its own linear-transition rules. */
export type ProjectUpdate = Partial<Omit<ProjectCreate, never>>;

export interface Project extends ProjectCreate {
  id: string;
  quote_id: string | null;
  status: ProjectStatus;
  created_at: string;
  assigned_user_id: string | null;
}
