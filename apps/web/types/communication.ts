/**
 * Communications (Sprint 039, Workstream A) — mirrors
 * app/communications/models.py's `CommunicationOut`.
 *
 * Sprint 038 built the ledger and its read endpoint; nothing in the
 * product ever showed it. These are the shapes that finally do.
 *
 * Two things this type deliberately does not carry, because the API
 * deliberately does not send them: the rendered message body, and any
 * provider internal (message ids, sender identity, raw error text).
 * `failure_detail` is sanitised server-side at write time and is safe to
 * show a user as-is.
 */

/**
 * Only states a real provider can actually establish. `delivered` is set
 * exclusively from a verified provider webhook — never assumed because a
 * send API accepted the request, which only ever produces `sent`.
 */
export const COMMUNICATION_STATUSES = [
  "draft",
  "queued",
  "sending",
  "sent",
  "delivered",
  "failed",
  "bounced",
  "suppressed",
] as const;

export type CommunicationStatus = (typeof COMMUNICATION_STATUSES)[number];

export interface Communication {
  id: string;
  tenant_id: string;
  customer_id: string | null;
  quote_id: string | null;
  project_id: string | null;
  invitation_id: string | null;
  automation_id: string | null;
  automation_run_id: string | null;
  channel: string;
  direction: string;
  message_type: string;
  recipient: string;
  subject: string;
  status: CommunicationStatus;
  attempt_count: number;
  last_attempted_at: string | null;
  failure_category: string | null;
  /** Sanitised at write time server-side — safe to show a user directly. */
  failure_detail: string | null;
  /**
   * Derived, never stored. A spam complaint proves the message *reached*
   * the inbox, so it never overwrites `status` — see sprint-039.md §4
   * Decision 1. A message can therefore be both `delivered` and
   * `complained`, which is exactly what happened.
   */
  complained: boolean;
  /** Whether the retry action applies. Served rather than re-derived here,
   * so this UI can never offer a retry the service would refuse. */
  retryable: boolean;
  created_at: string;
  updated_at: string;
}

export interface CommunicationFilters {
  customerId?: string;
  quoteId?: string;
  projectId?: string;
  invitationId?: string;
}
