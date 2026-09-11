"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { api } from "@/lib/api";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 1.
 *
 * The link a verification email actually points at
 * (`{frontend_base_url}/verify-email?token=...`, see
 * app/auth/verification_service.py). No auth is required to land here —
 * a person opening this on a different device/browser than the one they
 * signed up on must still be able to verify.
 *
 * Loaded with no `?token` at all, this instead shows the "we've sent you
 * a link, go check your inbox" state — reachable from Settings after
 * hitting "Resend verification email".
 */
type ConfirmState = "verifying" | "success" | "invalid" | "no-token";

function VerifyEmailContent() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");
  const { isAuthenticated } = useAuth();

  const [state, setState] = useState<ConfirmState>(token ? "verifying" : "no-token");

  useEffect(() => {
    if (!token) return;
    api
      .confirmEmailVerification(token)
      .then(() => setState("success"))
      .catch(() => setState("invalid"));
  }, [token]);

  return (
    <div className="mx-auto max-w-sm">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Verify your email
        </h1>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 py-6 text-center">
          {state === "verifying" && (
            <p className="text-sm text-muted">Confirming your email address…</p>
          )}

          {state === "success" && (
            <>
              <p className="text-sm text-foreground">
                Your email address has been verified.
              </p>
              <Button onClick={() => router.push(isAuthenticated ? "/customers" : "/login")}>
                {isAuthenticated ? "Continue to GeoCore" : "Sign in"}
              </Button>
            </>
          )}

          {state === "invalid" && (
            <>
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                This verification link is invalid or has expired.
              </p>
              <p className="text-sm text-muted">
                {isAuthenticated ? (
                  <>You can request a new one from Settings &rarr; Security.</>
                ) : (
                  <>
                    Sign in and request a new one from Settings &rarr; Security, or{" "}
                    <Link href="/login" className="text-accent hover:underline">
                      sign in
                    </Link>
                    .
                  </>
                )}
              </p>
            </>
          )}

          {state === "no-token" && (
            <p className="text-sm text-muted">
              We&apos;ve sent a verification link to your email address. Click it to
              verify your account.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
