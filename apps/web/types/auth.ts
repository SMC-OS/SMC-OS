export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string | null;
  // Sprint 009 — every user now belongs to exactly one tenant.
  tenant_id: string;
  tenant_name: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

/** Sprint 009 — creates a new company workspace + its first (Owner) user. */
export interface SignupRequest {
  company_name: string;
  name: string;
  email: string;
  password: string;
}
