"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { api } from "@/lib/api";

/**
 * Sprint 039 Production Readiness Defect Gate, Blocker 2.
 *
 * No auth required — a person who forgot their password is, by
 * definition, not signed in. Always shows the same success state on
 * submit regardless of whether the email exists (the backend's own
 * no-enumeration contract, app/auth/router.py's forgot_password) —
 * this page has no way to know either, and must not pretend otherwise.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.forgotPassword(email);
    } catch {
      // Deliberately ignored — see this page's own docstring above. A
      // network failure still shows the same generic confirmation
      // rather than revealing anything about the request's outcome.
    } finally {
      setSubmitting(false);
      setSubmitted(true);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Reset your password
        </h1>
        <p className="mt-1 text-sm text-muted">
          Enter your email and we&apos;ll send you a link to reset your password.
        </p>
      </div>

      <Card>
        <CardContent>
          {submitted ? (
            <p className="text-sm text-foreground">
              If an account exists for that email, we&apos;ve sent a reset link.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Field label="Email" htmlFor="email">
                <Input
                  id="email"
                  type="email"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="owner@geocore.one"
                />
              </Field>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Sending…" : "Send reset link"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      <p className="mt-4 text-center text-sm text-muted">
        <Link href="/login" className="text-accent hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  );
}
