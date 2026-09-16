"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { PasswordField } from "@/components/ui/PasswordField";
import { PasswordRequirements } from "@/components/ui/PasswordRequirements";
import { ApiError, api } from "@/lib/api";
import { passwordPolicyError } from "@/lib/passwordPolicy";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2.
 *
 * The link a reset email actually points at
 * (`{frontend_base_url}/reset-password?token=...`, see
 * app/auth/password_reset_service.py). No auth required — resetting a
 * forgotten password is, by definition, done while signed out.
 */
type ResetState = "form" | "success" | "invalid" | "no-token";

function ResetPasswordContent() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<ResetState>(token ? "form" : "no-token");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }
    const policyError = passwordPolicyError(password);
    if (policyError) {
      setError(policyError);
      return;
    }

    setSubmitting(true);
    try {
      await api.resetPassword(token as string, password);
      setState("success");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setState("invalid");
      } else if (err instanceof ApiError && err.status === 422) {
        setError(policyError ?? "Password does not meet the requirements below.");
      } else {
        setError("Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Set a new password
        </h1>
      </div>

      <Card>
        <CardContent className="py-6">
          {state === "no-token" && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              This reset link is missing its token. Request a new one from the{" "}
              <Link href="/forgot-password" className="underline">
                forgot password
              </Link>{" "}
              page.
            </p>
          )}

          {state === "invalid" && (
            <>
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                This reset link is invalid or has expired.
              </p>
              <Button
                className="mt-4"
                onClick={() => router.push("/forgot-password")}
              >
                Request a new link
              </Button>
            </>
          )}

          {state === "success" && (
            <>
              <p className="text-sm text-foreground">
                Your password has been reset. Please sign in again.
              </p>
              <Button className="mt-4" onClick={() => router.push("/login")}>
                Sign in
              </Button>
            </>
          )}

          {state === "form" && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <PasswordField
                id="password"
                label="New password"
                autoComplete="new-password"
                required
                autoFocus
                value={password}
                onChange={setPassword}
              />
              <PasswordRequirements password={password} />
              <PasswordField
                id="confirmPassword"
                label="Confirm new password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={setConfirmPassword}
              />

              {error && (
                <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                  {error}
                </p>
              )}

              <Button type="submit" disabled={submitting}>
                {submitting ? "Resetting…" : "Reset password"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}
