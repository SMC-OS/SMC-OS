// Sprint 016 — mirrors app/documents/models.py's DocumentOut.

export interface DocumentOut {
  id: string;
  tenant_id: string;
  customer_id: string;
  uploaded_by_user_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}
