import {
  BotIcon,
  CheckCircleIcon,
  FileTextIcon,
  FolderIcon,
  UserIcon,
  UsersIcon,
} from "@/components/ui/icons";
import type { ActivityType } from "@/types/activity";

export const ACTIVITY_ICON: Record<ActivityType, typeof BotIcon> = {
  quote_created: FileTextIcon,
  customer_added: UsersIcon,
  project_created: FolderIcon,
  invoice_generated: CheckCircleIcon,
  ai_request: BotIcon,
  user_login: UserIcon,
};

export const ACTIVITY_TONE: Record<ActivityType, string> = {
  quote_created: "bg-info/10 text-info",
  customer_added: "bg-accent/10 text-accent",
  project_created: "bg-warning/10 text-warning",
  invoice_generated: "bg-success/10 text-success",
  ai_request: "bg-accent/10 text-accent",
  user_login: "bg-surface-hover text-muted",
};
