// Sprint 011 — mirrors app/invitations/models.py.

export interface InvitationOut {
  id: string;
  tenant_id: string;
  email: string;
  role: string;
  status: string;
  invited_by_user_id: string;
  expires_at: string;
  created_at: string;
}

/** Same shape as InvitationOut, plus the one-time raw token — only ever
 * returned from the create-invitation response. */
export interface InvitationCreateOut extends InvitationOut {
  token: string;
}

/** What an unauthenticated invitee sees before deciding whether to accept —
 * no internal IDs. */
export interface InvitationPublicOut {
  email: string;
  role: string;
  tenant_name: string;
  status: string;
  expires_at: string;
}

export interface AcceptInvitationRequest {
  name: string;
  password: string;
}
