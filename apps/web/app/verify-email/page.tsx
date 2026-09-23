"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 1.
 *
 * The link a verification email actually points at
 * (`{frontend_base_url}/verify-email?token=...`, see
 * app/auth/verification_service.py). No auth is required to land here —
 * a person opening this on a different device/browser than the one they
 * signed up on must still be able to verify.
 *
 * Loaded with no `?token` at all, this is the "verification required"
 * holding screen: AppShell (Sprint 039 Blocker 2 hotfix) redirects every
 * authenticated-but-unverified user here for any route this narrow
 * allowlist doesn't cover, so this state must be fully self-sufficient —
 * resend, sign out, nothing else needed to get unstuck.
 *
 * Sprint 039 Blocker 2 follow-up (verification resend/token hotfix) —
 * confirmed live on staging: a SECOND view of the same, already-
 * successfully-used link (a mail client re-opening it, a double-tap, a
 * link-prescanning security proxy) gets the identical 400 a genuinely
 * bad/expired token would, by design — replay-rejection is a security
 * invariant this file does not relax (app/auth/verification_service.py's
 * verify() is unchanged). What was wrong is presentation: a bare
 * "invalid or expired" left an actually-already-verified owner thinking
 * verification had failed. The fix reads this browser's own live auth
 * state (refreshed via /auth/me on mount, so it is never stale) rather
 * than trusting confirm()'s specific failure reason, which this page was
 * never told and must not need.
 */
type ConfirmOutcome = "pending" | "success" | "failed";
type ConfirmState = "verifying" | "success" | "already-verified" | "invalid" | "no-token";
type ResendState = "idle" | "sending" | "sent" | "already-verified" | "cooldown" | "error";

function VerifyEmailContent() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token");
  const { isReady, isAuthenticated, verificationRequired, email, logout } = useAuth();

  const [confirmOutcome, setConfirmOutcome] = useState<ConfirmOutcome>(
    token ? "pending" : "success"
  );
  const [resendState, setResendState] = useState<ResendState>("idle");

  useEffect(() => {
    if (!token) return;
    api
      .confirmEmailVerification(token)
      .then(() => setConfirmOutcome("success"))
      .catch(() => setConfirmOutcome("failed"));
  }, [token]);

  // Derived, not stored: a failed confirm is ambiguous on its own (see
  // this file's docstring above) — waiting for isReady before committing
  // to "invalid" avoids a flash of the wrong, scarier state.
  const state: ConfirmState = !token
    ? "no-token"
    : confirmOutcome === "pending"
      ? "verifying"
      : confirmOutcome === "success"
        ? "success"
        : !isReady
          ? "verifying"
          : isAuthenticated && !verificationRequired
            ? "already-verified"
            : "invalid";

  async function handleResend() {
    setResendState("sending");
    try {
      const result = await api.resendVerificationEmail();
      setResendState(result.already_verified ? "already-verified" : "sent");
    } catch (err) {
      // Sprint 039 Blocker 2 hotfix — the resend cooldown (app.auth.
      // rate_limit's CooldownLimiter) returns 429; every other failure
      // (network, 5xx) gets the generic message. Neither ever reveals
      // whether a *different* address has an account — this button only
      // ever acts on the signed-in user's own session.
      setResendState(err instanceof ApiError && err.status === 429 ? "cooldown" : "error");
    }
  }

  function handleLogout() {
    logout();
    router.push("/login");
  }

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
              <Button onClick={() => router.push(isAuthenticated ? "/onboarding" : "/login")}>
                {isAuthenticated ? "Continue to GeoCore" : "Sign in"}
              </Button>
            </>
          )}

          {state === "already-verified" && (
            <>
              <p className="text-sm text-foreground">
                Your email address is already verified — you&apos;re all set.
              </p>
              <Button onClick={() => router.push("/onboarding")}>Continue to GeoCore</Button>
            </>
          )}

          {state === "invalid" && (
            <>
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                This verification link is invalid or has expired.
              </p>
              <p className="text-sm text-muted">
                {isAuthenticated ? (
                  <>Request a new link below.</>
                ) : (
                  <>
                    Sign in and request a new one, or{" "}
                    <Link href="/login" className="text-accent hover:underline">
                      sign in
                    </Link>
                    .
                  </>
                )}
              </p>
              {isAuthenticated && (
                <ResendControl resendState={resendState} onResend={handleResend} />
              )}
            </>
          )}

          {state === "no-token" && (
            <>
              <p className="text-sm text-foreground">
                We&apos;ve sent a verification link to{" "}
                {email ? <span className="font-medium">{email}</span> : "your email address"}.
                Verify your email to continue to GeoCore.
              </p>
              {isAuthenticated ? (
                <>
                  <ResendControl resendState={resendState} onResend={handleResend} />
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="text-sm text-muted hover:text-foreground hover:underline"
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <p className="text-sm text-muted">
                  Already verified?{" "}
                  <Link href="/login" className="text-accent hover:underline">
                    Sign in
                  </Link>
                  .
                </p>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ResendControl({
  resendState,
  onResend,
}: {
  resendState: ResendState;
  onResend: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="outline"
        onClick={onResend}
        disabled={resendState === "sending"}
      >
        {resendState === "sending" ? "Sending…" : "Resend verification email"}
      </Button>
      {resendState === "sent" && (
        <p className="text-sm text-success">Verification email sent — check your inbox.</p>
      )}
      {resendState === "already-verified" && (
        <p className="text-sm text-success">Your email is already verified — you&apos;re all set.</p>
      )}
      {resendState === "cooldown" && (
        <p className="text-sm text-muted">
          Please wait a little before requesting another one.
        </p>
      )}
      {resendState === "error" && (
        <p className="text-sm text-danger">Something went wrong. Try again shortly.</p>
      )}
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
