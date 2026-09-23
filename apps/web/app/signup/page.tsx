"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { PasswordField } from "@/components/ui/PasswordField";
import { PasswordRequirements } from "@/components/ui/PasswordRequirements";
import { ApiError } from "@/lib/api";
import { passwordPolicyError } from "@/lib/passwordPolicy";

// Phase B — the plan chosen on the public pricing page arrives as
// ?plan=&billing_period= and is carried into signup, so the no-card
// trial starts on it and nobody picks the same plan twice. Only known
// self-service plans are forwarded; anything else signs up on the
// default trial plan (the API applies the same rule).
const TRIAL_PLAN_LABELS: Record<string, string> = {
  starter: "Starter",
  team: "Team",
  pro: "Pro",
  business: "Business",
};
const BILLING_PERIOD_LABELS: Record<string, string> = {
  monthly: "monthly billing",
  annual: "annual billing",
};

export default function SignupPage() {
  // useSearchParams needs a Suspense boundary in the App Router, same as
  // app/quotes/new/page.tsx.
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { signup } = useAuth();

  const requestedPlan = params.get("plan") ?? "";
  const requestedPeriod = params.get("billing_period") ?? "";
  const plan = requestedPlan in TRIAL_PLAN_LABELS ? requestedPlan : null;
  const billingPeriod = plan && requestedPeriod in BILLING_PERIOD_LABELS ? requestedPeriod : null;

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
    const policyError = passwordPolicyError(password);
    if (policyError) {
      setError(policyError);
      return;
    }

    setSubmitting(true);

    try {
      const required = await signup({
        company_name: companyName,
        name,
        email,
        password,
        ...(plan ? { plan } : {}),
        ...(billingPeriod ? { billing_period: billingPeriod } : {}),
      });
      // Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
      // a brand-new signup is unverified and must land on the
      // verification screen, not straight into the workspace.
      //
      // GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES — once verified, a
      // brand-new workspace has no Subscription yet and must choose a
      // plan before anything else, not go straight to onboarding.
      //
      // Sprint 036 (Workstream J) — once BOTH are satisfied, a brand-new
      // workspace goes to setup, not to an empty customer list.
      // /onboarding sends an already-established workspace straight
      // on, so this is safe for anyone who somehow reaches it with
      // data already in place.
      router.push(
        required.verificationRequired
          ? "/verify-email"
          : required.billingAccessRequired
            ? "/pricing"
            : "/onboarding"
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("An account with that email already exists.");
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

      <div
        className="mb-4 rounded-lg border border-border bg-surface px-4 py-3 text-sm"
        data-testid="trial-summary"
      >
        <p className="font-medium text-foreground">14-day free trial. No card required.</p>
        <p className="mt-1 text-muted">
          {plan
            ? `You're starting a free trial of GeoCore ${TRIAL_PLAN_LABELS[plan]}${
                billingPeriod ? ` (${BILLING_PERIOD_LABELS[billingPeriod]})` : ""
              }. Nothing is charged when it ends — choose a plan only if you want to keep going.`
            : "Your workspace is ready as soon as you verify your email. Nothing is charged when the trial ends — choose a plan only if you want to keep going."}
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
            <PasswordRequirements password={password} />
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
              {submitting ? "Creating workspace…" : "Create workspace and start free trial"}
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
