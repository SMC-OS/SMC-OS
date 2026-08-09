export type ActivityType =
  | "quote_created"
  | "customer_added"
  | "project_created"
  | "invoice_generated"
  | "ai_request"
  | "user_login";

export interface ActivityEvent {
  id: string;
  type: ActivityType;
  title: string;
  description?: string | null;
  timestamp: string;
}
