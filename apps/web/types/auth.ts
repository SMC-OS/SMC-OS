export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: string | null;
  // Sprint 009 — every user now belongs to exactly one tenant.
  tenant_id: string;
  tenant_name: string;
  // Sprint 039 Production Readiness Defect Gate, Blocker 1 — null means
  // unverified (including every legacy user); an ISO timestamp string is
  // when verification happened.
  email_verified_at: string | null;
  // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
  // whether this user is CURRENTLY blocked from normal application
  // access. Route on this, not on email_verified_at directly: a legacy
  // user within their grace period has email_verified_at=null but
  // verification_required=false, and only the backend
  // (app.auth.dependencies.is_verification_required) knows that.
  verification_required: boolean;
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
