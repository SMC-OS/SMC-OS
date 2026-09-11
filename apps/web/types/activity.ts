// Sprint 025 finding (docs/SPRINTS/sprint-025.md): this union had drifted
// out of sync with the backend's ActivityType enum (app/activity/models.py)
// since Sprint 020 — 13 real, long-emitted event types were missing here,
// which crashed the entire dashboard page (not just Recent Activity) the
// first time any of them appeared in a real activity feed, because
// lib/activity.ts's icon/tone lookups returned undefined for an unmapped
// type. Fixed by widening this union and the two lookup maps to the full
// backend enum.
export type ActivityType =
  | "quote_created"
  | "customer_added"
  | "project_created"
  | "invoice_generated"
  | "ai_request"
  | "user_login"
  | "tenant_created"
  | "tenant_identity_updated"
  | "portal_link_created"
  | "team_member_deactivated"
  | "customer_message_received"
  | "quote_approved"
  | "quote_handed_off"
  | "enquiry_converted"
  | "site_visit_scheduled"
  | "site_visit_completed"
  | "site_visit_cancelled"
  | "project_assigned"
  | "project_status_changed"
  // Sprint 036
  | "automation_created"
  | "task_completed"
  // Sprint 039 Production Readiness Defect Gate, Blocker 1
  | "email_verification_requested"
  | "email_verified"
  // Sprint 039 Production Readiness Defect Gate, Blocker 2
  | "password_reset_requested"
  | "password_changed";

export interface ActivityEvent {
  id: string;
  type: ActivityType;
  title: string;
  description?: string | null;
  timestamp: string;
}
