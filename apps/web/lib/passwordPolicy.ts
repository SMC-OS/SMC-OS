/**
 * Sprint 039 Production Readiness Defect Gate, final auth gate.
 *
 * Mirrors app/auth/password_policy.py exactly (minimum length + the
 * same four character-class requirements, in the same order) so the
 * requirements shown here and the ones the backend actually enforces
 * never drift apart. This file is NOT the security boundary — every
 * one of signup, reset-password and invite-accept still sends the raw
 * password to the backend, which re-validates it independently
 * (app/auth/models.py's SignupRequest/ResetPasswordRequest,
 * app/invitations/models.py's AcceptInvitationRequest). This only
 * gives the user a useful checklist before they submit.
 */

export const PASSWORD_MIN_LENGTH = 10;

export interface PasswordRequirement {
  id: string;
  label: string;
  test: (password: string) => boolean;
}

export const PASSWORD_REQUIREMENTS: PasswordRequirement[] = [
  {
    id: "length",
    label: `At least ${PASSWORD_MIN_LENGTH} characters`,
    test: (password) => password.length >= PASSWORD_MIN_LENGTH,
  },
  {
    id: "uppercase",
    label: "One uppercase letter",
    test: (password) => /[A-Z]/.test(password),
  },
  {
    id: "lowercase",
    label: "One lowercase letter",
    test: (password) => /[a-z]/.test(password),
  },
  {
    id: "number",
    label: "One number",
    test: (password) => /[0-9]/.test(password),
  },
  {
    id: "symbol",
    label: "One special character",
    test: (password) => /[^A-Za-z0-9]/.test(password),
  },
];

/** First unmet requirement's message, or null if the password satisfies all of them. */
export function passwordPolicyError(password: string): string | null {
  const failed = PASSWORD_REQUIREMENTS.find((requirement) => !requirement.test(password));
  return failed ? `Password must include: ${failed.label.toLowerCase()}.` : null;
}

export function passwordSatisfiesPolicy(password: string): boolean {
  return PASSWORD_REQUIREMENTS.every((requirement) => requirement.test(password));
}
