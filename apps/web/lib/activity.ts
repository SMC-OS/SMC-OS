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
};
