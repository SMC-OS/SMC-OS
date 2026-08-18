// Sprint 017 — mirrors app/messages/models.py's MessageOut. Shared by both
// the staff-side thread (customers/[id]) and the public portal thread
// (portal/[token]) — sender_type ("staff"|"customer") is what a component
// switches on to render "you" vs "them".

export interface MessageOut {
  id: string;
  tenant_id: string;
  customer_id: string;
  sender_type: "staff" | "customer";
  sender_user_id: string | null;
  body: string;
  created_at: string;
}
