"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import type { InvitationPublicOut } from "@/types/invitation";

const UNUSABLE_MESSAGES: Record<string, string> = {
  revoked: "This invitation has been revoked. Ask your workspace owner for a new one.",
  accepted: "This invitation has already been used — sign in instead.",
  expired: "This invitation link has expired. Ask your workspace owner to send a new one.",
};

export default function AcceptInvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { acceptInvite } = useAuth();

  const [invite, setInvite] = useState<InvitationPublicOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getInvitationByToken(params.token)
      .then(setInvite)
      .catch((err) =>
        setLoadError(
          err instanceof ApiError && err.status === 404
            ? "This invitation link isn't valid."
            : "Something went wrong."
        )
      );
  }, [params.token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);

    try {
      await acceptInvite(params.token, { name, password });
      router.push("/customers");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setSubmitError("This invitation link isn't valid.");
      } else if (err instanceof ApiError && err.status === 409) {
        setSubmitError(
          "This invitation can no longer be accepted — it may have just been used, revoked, or expired."
        );
      } else {
        setSubmitError("Something went wrong.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Join your team
        </h1>
        {invite && (
          <p className="mt-1 text-sm text-muted">
            You&apos;ve been invited to join{" "}
            <span className="font-medium text-foreground">{invite.tenant_name}</span>{" "}
            as {invite.role}.
          </p>
        )}
      </div>

      <Card>
        <CardContent>
          {loadError && (
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {loadError}
            </p>
          )}

          {!loadError && invite === null && (
            <p className="text-center text-sm text-muted">Loading…</p>
          )}

          {!loadError && invite && invite.status !== "pending" && (
            <p className="rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
              {UNUSABLE_MESSAGES[invite.status] ?? "This invitation can no longer be used."}
            </p>
          )}

          {!loadError && invite && invite.status === "pending" && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <Field label="Email" htmlFor="inviteAcceptEmail">
                <Input id="inviteAcceptEmail" value={invite.email} disabled />
              </Field>
              <Field label="Your name" htmlFor="inviteAcceptName">
                <Input
                  id="inviteAcceptName"
                  required
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Jane Doe"
                />
              </Field>
              <Field label="Password" htmlFor="inviteAcceptPassword">
                <Input
                  id="inviteAcceptPassword"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </Field>

              {submitError && (
                <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                  {submitError}
                </p>
              )}

              <Button type="submit" disabled={submitting}>
                {submitting ? "Joining…" : "Accept invitation"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
