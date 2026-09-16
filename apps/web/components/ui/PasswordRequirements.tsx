"use client";

import { PASSWORD_REQUIREMENTS } from "@/lib/passwordPolicy";

/**
 * Sprint 039 Production Readiness Defect Gate, final auth gate — live
 * checklist shown under a new-password field on signup, reset-password
 * and invite-accept. Purely informational: the backend is the
 * authoritative check (see apps/web/lib/passwordPolicy.ts's docstring).
 */
export function PasswordRequirements({ password }: { password: string }) {
  return (
    <ul className="flex flex-col gap-0.5 text-xs text-muted" aria-label="Password requirements">
      {PASSWORD_REQUIREMENTS.map((requirement) => {
        const met = requirement.test(password);
        return (
          <li
            key={requirement.id}
            className={met ? "text-success" : "text-muted"}
            data-met={met}
          >
            {met ? "✓" : "•"} {requirement.label}
          </li>
        );
      })}
    </ul>
  );
}
