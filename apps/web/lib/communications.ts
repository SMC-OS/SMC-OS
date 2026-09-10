import type { BadgeTone } from "@/lib/projects";
import type { Communication, CommunicationStatus } from "@/types/communication";

/**
 * How a communication reads to a user (Sprint 039, Workstream A).
 *
 * The vocabulary problem this solves: the ledger's own words are
 * engineering words. "queued", "suppressed" and "unavailable" are precise
 * and worth keeping in the database, and none of them are what someone
 * running a building firm wants to read at eight in the morning. Every
 * mapping here turns one into plain English **without softening what
 * actually happened** — a failed send still says it failed.
 */

/** What each delivery state means, in the customer's language. */
export const STATUS_LABEL: Record<CommunicationStatus, string> = {
  draft: "Draft",
  queued: "Queued",
  sending: "Sending",
  sent: "Sent",
  delivered: "Delivered",
  failed: "Failed",
  bounced: "Bounced",
  suppressed: "Not sent",
};

export const STATUS_TONE: Record<CommunicationStatus, BadgeTone> = {
  draft: "neutral",
  queued: "neutral",
  sending: "info",
  // "Sent" is deliberately `info`, not `success`: the provider accepted
  // it, which is not the same as it having arrived. Only `delivered` —
  // which comes exclusively from a verified provider webhook — is a
  // success, and the difference is the whole reason Sprint 038 kept two
  // separate states.
  sent: "info",
  delivered: "success",
  failed: "danger",
  bounced: "danger",
  suppressed: "warning",
};

/**
 * A one-line explanation of the state, shown under the status badge.
 * Present only where the state genuinely needs explaining — "Delivered"
 * explains itself and gets nothing.
 */
export const STATUS_HINT: Partial<Record<CommunicationStatus, string>> = {
  queued: "Waiting to go out.",
  sending: "Going out now.",
  sent: "Accepted by the mail provider. Not confirmed as arrived yet.",
  bounced: "The address rejected it. It's been added to your do-not-send list.",
  suppressed: "This address is on your do-not-send list, so nothing was sent.",
};

/** What kind of message this was, in plain English. */
export const MESSAGE_TYPE_LABEL: Record<string, string> = {
  invitation: "Team invitation",
  quote_sent: "Quote",
  quote_follow_up: "Quote follow-up",
  project_confirmation: "Project confirmation",
  project_update: "Project update",
  project_completion: "Project completed",
  review_request: "Review request",
};

export function messageTypeLabel(messageType: string): string {
  // Falls back to a de-underscored version of the stored value rather than
  // to "Other": a type this build has not been taught about is still more
  // useful shown than hidden.
  return (
    MESSAGE_TYPE_LABEL[messageType] ??
    messageType.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())
  );
}

/**
 * The single line that tells a user what to do about a failure, derived
 * from the failure category rather than from the raw provider text.
 * `failure_detail` is sanitised server-side and shown alongside this.
 */
export function failureGuidance(communication: Communication): string | null {
  if (communication.status === "bounced") {
    return "Check the address with your customer — a corrected one can be sent to normally.";
  }
  switch (communication.failure_category) {
    case "transient":
      return "A temporary problem at the mail provider. GeoCore retries these automatically, and you can try again now.";
    case "unavailable":
      return "No email provider is connected to this workspace yet, so nothing was sent.";
    case "permanent":
      return "The mail provider rejected this and will keep rejecting it. Check the address.";
    case "suppressed":
      return "This address is on your do-not-send list, usually after a bounce or a spam complaint.";
    default:
      return null;
  }
}

/** Which record this message was about, for the "Related to" column. */
export function relatedEntity(
  communication: Communication
): { label: string; href: string } | null {
  if (communication.quote_id) {
    return { label: "Quote", href: `/quotes/${communication.quote_id}` };
  }
  if (communication.project_id) {
    return { label: "Project", href: `/projects/${communication.project_id}` };
  }
  if (communication.customer_id) {
    return { label: "Customer", href: `/customers/${communication.customer_id}` };
  }
  // An invitation has no page of its own — it lives in Settings → Team.
  if (communication.invitation_id) {
    return { label: "Team invitation", href: "/settings?section=team" };
  }
  return null;
}
