// Sprint 015 — mirrors app/users/models.py's TeamMemberOut.

export interface TeamMemberOut {
  id: string;
  name: string;
  email: string;
  role: string | null;
  is_active: boolean;
  created_at: string;
}
