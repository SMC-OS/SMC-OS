/**
 * Projects and the trade-neutral pipeline (Sprint 039, Workstream D).
 *
 * Sprint 036 left a note here saying "templated" and "fabricated" are
 * stone-industry stages that make no sense for a roofing or decorating
 * job, and that renaming the pipeline was real work deliberately deferred
 * rather than half-done. This is that work.
 *
 * The change in one line: **what a stage is called is tenant
 * configuration; what it means is a fixed role.** There is no hardcoded
 * list of statuses in the frontend any more — a tenant's stages come from
 * `GET /projects/meta/pipeline`, and anything this app needs to *reason*
 * about (is this job finished? is it on hold?) keys off `PipelineRole`,
 * which is the same eight values for every business on GeoCore.
 *
 * Stone/worktop businesses keep their vocabulary. It is a template now,
 * not GeoCore's identity.
 */

/** The trade-neutral vocabulary. Mirrors app/projects/pipeline.py's ROLES. */
export const PIPELINE_ROLES = [
  "lead",
  "quoted",
  "approved",
  "scheduled",
  "in_progress",
  "on_hold",
  "completed",
  "cancelled",
] as const;

export type PipelineRole = (typeof PIPELINE_ROLES)[number];

/**
 * One stage of the current tenant's own pipeline.
 *
 * `allowed_transitions` comes from the backend rather than being derived
 * here, so this UI can never offer a move the engine would refuse — the
 * same reason the automations builder reads its triggers and actions from
 * `/automations/meta`.
 */
export interface PipelineStage {
  key: string;
  label: string;
  role: PipelineRole;
  position: number;
  is_terminal: boolean;
  is_side_state: boolean;
  allowed_transitions: string[];
}

export interface ProjectPipeline {
  stages: PipelineStage[];
}

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
 * with its own transition rules. */
export type ProjectUpdate = Partial<Omit<ProjectCreate, never>>;

export interface Project extends ProjectCreate {
  id: string;
  quote_id: string | null;
  /** A stage key from this tenant's own pipeline — not a fixed enum. */
  status: string;
  /** The trade-neutral meaning of that stage. Null only for a project
   * sitting on a stage its tenant has since reconfigured away. */
  status_role: PipelineRole | null;
  created_at: string;
  assigned_user_id: string | null;
}
