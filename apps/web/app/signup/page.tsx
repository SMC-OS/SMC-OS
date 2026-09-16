"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { PasswordField } from "@/components/ui/PasswordField";
import { ApiError } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const { signup } = useAuth();

  const [companyName, setCompanyName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);

    try {
      const verificationRequired = await signup({ company_name: companyName, name, email, password });
      // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
      // a brand-new signup is unverified and must land on the
      // verification screen, not straight into the workspace.
      //
      // Sprint 036 (Workstream J) — once verified, a brand-new
      // workspace goes to setup, not to an empty customer list.
      // /onboarding sends an already-established workspace straight
      // on, so this is safe for anyone who somehow reaches it with
      // data already in place.
      router.push(verificationRequired ? "/verify-email" : "/onboarding");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "An account with that email already exists."
          : "Something went wrong."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Create your workspace
        </h1>
        <p className="mt-1 text-sm text-muted">
          {/* Sprint 036 (Workstream J) — neutral copy. The previous
              placeholders ("Acme Stoneworks", "jane@acmestoneworks.com")
              told every plumber, roofer and decorator signing up that
              this product was not for them, before they had entered a
              single field. */}
          GeoCore is for construction and renovation businesses — building,
          extensions, kitchens, bathrooms, roofing, electrics, stone and
          everything in between.
        </p>
      </div>

      <Card>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Field label="Company name" htmlFor="companyName">
              <Input
                id="companyName"
                required
                autoFocus
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="e.g. Hartley Building Ltd"
              />
            </Field>
            <Field label="Your name" htmlFor="name">
              <Input
                id="name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Sam Hartley"
              />
            </Field>
            <Field label="Email" htmlFor="email">
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@yourcompany.co.uk"
              />
            </Field>
            <PasswordField
              id="password"
              label="Password"
              autoComplete="new-password"
              required
              value={password}
              onChange={setPassword}
            />
            <PasswordField
              id="confirmPassword"
              label="Confirm password"
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
              {submitting ? "Creating workspace…" : "Create workspace"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <p className="mt-4 text-center text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-accent hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
