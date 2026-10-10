import {
  AlertTriangleIcon,
  BotIcon,
  CheckCircleIcon,
  FileTextIcon,
  FolderIcon,
  InfoIcon,
  SettingsIcon,
  UserIcon,
  UsersIcon,
  ZapIcon,
} from "@/components/ui/icons";
import type { ActivityType } from "@/types/activity";

// Sprint 025 finding (docs/SPRINTS/sprint-025.md) — kept in sync with the
// full backend ActivityType enum (app/activity/models.py), not just the
// original 6 values from Sprint 007. See types/activity.ts's comment.
export const ACTIVITY_ICON: Record<ActivityType, typeof BotIcon> = {
  quote_created: FileTextIcon,
  customer_added: UsersIcon,
  project_created: FolderIcon,
  invoice_generated: CheckCircleIcon,
  ai_request: BotIcon,
  user_login: UserIcon,
  tenant_created: UsersIcon,
  tenant_identity_updated: SettingsIcon,
  portal_link_created: FileTextIcon,
  team_member_deactivated: UserIcon,
  customer_message_received: InfoIcon,
  quote_approved: CheckCircleIcon,
  quote_handed_off: FolderIcon,
  enquiry_converted: UsersIcon,
  site_visit_scheduled: FileTextIcon,
  site_visit_completed: CheckCircleIcon,
  site_visit_cancelled: AlertTriangleIcon,
  project_assigned: UserIcon,
  project_status_changed: FolderIcon,
  // Sprint 036
  automation_created: ZapIcon,
  task_completed: CheckCircleIcon,
  // Sprint 039 Production Readiness Defect Gate, Blocker 1
  email_verification_requested: InfoIcon,
  email_verified: CheckCircleIcon,
  // Sprint 039 Production Readiness Defect Gate, Blocker 2
  password_reset_requested: InfoIcon,
  password_changed: CheckCircleIcon,
  demo_request_received: UsersIcon,
  project_cost_added: FileTextIcon,
  project_cost_edited: FileTextIcon,
  project_cost_deleted: AlertTriangleIcon,
  variation_created: FileTextIcon,
  variation_sent: FileTextIcon,
  variation_approved: CheckCircleIcon,
  variation_rejected: AlertTriangleIcon,
  variation_voided: AlertTriangleIcon,
  material_requirement_created: FileTextIcon,
  material_requirement_edited: FileTextIcon,
  material_requirement_cancelled: AlertTriangleIcon,
  purchase_order_created: FileTextIcon,
  purchase_order_approved: CheckCircleIcon,
  purchase_order_ordered: FileTextIcon,
  purchase_order_cancelled: AlertTriangleIcon,
  purchase_order_receipt_recorded: FileTextIcon,
  material_allocated: CheckCircleIcon,
};

export const ACTIVITY_TONE: Record<ActivityType, string> = {
  quote_created: "bg-info/10 text-info",
  customer_added: "bg-accent/10 text-accent",
  project_created: "bg-warning/10 text-warning",
  invoice_generated: "bg-success/10 text-success",
  ai_request: "bg-accent/10 text-accent",
  user_login: "bg-surface-hover text-muted",
  tenant_created: "bg-accent/10 text-accent",
  tenant_identity_updated: "bg-accent/10 text-accent",
  portal_link_created: "bg-info/10 text-info",
  team_member_deactivated: "bg-surface-hover text-muted",
  customer_message_received: "bg-info/10 text-info",
  quote_approved: "bg-success/10 text-success",
  quote_handed_off: "bg-success/10 text-success",
  enquiry_converted: "bg-success/10 text-success",
  site_visit_scheduled: "bg-info/10 text-info",
  site_visit_completed: "bg-success/10 text-success",
  site_visit_cancelled: "bg-warning/10 text-warning",
  project_assigned: "bg-accent/10 text-accent",
  project_status_changed: "bg-warning/10 text-warning",
  // Sprint 036
  automation_created: "bg-champagne-subtle text-champagne",
  task_completed: "bg-success/10 text-success",
  // Sprint 039 Production Readiness Defect Gate, Blocker 1
  email_verification_requested: "bg-info/10 text-info",
  email_verified: "bg-success/10 text-success",
  // Sprint 039 Production Readiness Defect Gate, Blocker 2
  password_reset_requested: "bg-info/10 text-info",
  password_changed: "bg-success/10 text-success",
  demo_request_received: "bg-info/10 text-info",
  project_cost_added: "bg-info/10 text-info",
  project_cost_edited: "bg-info/10 text-info",
  project_cost_deleted: "bg-info/10 text-info",
  variation_created: "bg-info/10 text-info",
  variation_sent: "bg-info/10 text-info",
  variation_approved: "bg-info/10 text-info",
  variation_rejected: "bg-info/10 text-info",
  variation_voided: "bg-info/10 text-info",
  material_requirement_created: "bg-info/10 text-info",
  material_requirement_edited: "bg-info/10 text-info",
  material_requirement_cancelled: "bg-info/10 text-info",
  purchase_order_created: "bg-info/10 text-info",
  purchase_order_approved: "bg-info/10 text-info",
  purchase_order_ordered: "bg-info/10 text-info",
  purchase_order_cancelled: "bg-info/10 text-info",
  purchase_order_receipt_recorded: "bg-info/10 text-info",
  material_allocated: "bg-info/10 text-info",
};

// Runtime responses can advance before the web bundle during a rolling release.
// Keep the event itself visible; an unfamiliar category gets neutral styling.
export function activityPresentation(type: string) {
  const known = Object.hasOwn(ACTIVITY_ICON, type);
  return {
    Icon: known ? ACTIVITY_ICON[type as ActivityType] : InfoIcon,
    tone: known ? ACTIVITY_TONE[type as ActivityType] : "bg-surface-hover text-muted",
  };
}
