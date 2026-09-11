/**
 * GeoCore AI drafting (Sprint 039, Workstream C) — mirrors
 * app/ai/drafting.py.
 *
 * Note what `Draft` does not carry: no `sent`, no `recipient`, no
 * communication id, no status. The backend shape has no such field
 * either, which is what makes "the AI sent it" structurally impossible
 * rather than merely discouraged. Sending is a separate call, made by a
 * person, after reading the text.
 */

export const DRAFT_KINDS = [
  "quote_delivery",
  "quote_follow_up",
  "project_update",
  "appointment_update",
  "payment_reminder",
  "general",
] as const;

export type DraftKind = (typeof DRAFT_KINDS)[number];

export const DRAFT_KIND_LABELS: Record<DraftKind, string> = {
  quote_delivery: "Send a quote",
  quote_follow_up: "Follow up a quote",
  project_update: "Update on the job",
  appointment_update: "Confirm or change a visit",
  payment_reminder: "Payment reminder",
  general: "Something else",
};

export const REWRITE_INSTRUCTIONS = [
  "shorten",
  "expand",
  "warmer",
  "more_formal",
  "simpler",
] as const;

export type RewriteInstruction = (typeof REWRITE_INSTRUCTIONS)[number];

export const REWRITE_LABELS: Record<RewriteInstruction, string> = {
  shorten: "Shorter",
  expand: "Longer",
  warmer: "Warmer",
  more_formal: "More formal",
  simpler: "Simpler",
};

export const TONES = ["friendly", "professional", "direct"] as const;
export type Tone = (typeof TONES)[number];

export interface Draft {
  kind: string;
  subject: string;
  body: string;
  engine: string;
  /** The records the model was shown, in plain language — so a reviewer
   * can judge whether to trust what it wrote rather than guess what it
   * knew. */
  grounded_in: string[];
}

export interface DraftRequest {
  kind: DraftKind;
  customer_id?: string;
  quote_id?: string;
  project_id?: string;
  tone?: Tone;
  notes?: string;
}

export interface CustomerMessageRequest {
  customer_id: string;
  kind: DraftKind;
  subject: string;
  body: string;
  quote_id?: string;
  project_id?: string;
  /** Generated when the compose panel opens and reused if Send is pressed
   * twice, so a double click resolves to the same communication rather
   * than sending two emails. */
  idempotency_key?: string;
}
