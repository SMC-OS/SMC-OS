"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { InvitationCreateOut, InvitationOut } from "@/types/invitation";
import type { TeamMemberOut } from "@/types/user";

const STATUS_TONE: Record<string, "info" | "success" | "neutral" | "warning"> = {
  pending: "info",
  accepted: "success",
  revoked: "neutral",
  expired: "warning",
};

/**
 * Team & permissions — Sprint 036, Workstream I.
 *
 * The developer-facing copy this replaces read: "There's no email
 * delivery yet — copy the generated link and send it yourself." That is
 * an implementation limitation stated as a product instruction, and it is
 * the kind of sentence that tells a paying customer the software is
 * unfinished.
 *
 * The underlying fact is unchanged — GeoCore genuinely cannot send email
 * — so this does not pretend otherwise. What changes is that the flow is
 * designed around it: the invitation link is presented as the deliberate
 * output of the action, ready to copy into whatever the person already
 * uses to talk to their team, with its expiry stated. Honest, and no
 * longer an apology.
 */
export function TeamCard() {
  const [members, setMembers] = useState<TeamMemberOut[] | null>(null);
  const [invitations, setInvitations] = useState<InvitationOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [created, setCreated] = useState<InvitationCreateOut | null>(null);
  const [copied, setCopied] = useState(false);
  const [deactivating, setDeactivating] = useState<string | null>(null);

  const load = useCallback(() => {
    api.getUsers().then(setMembers).catch(() => setError("Could not load your team."));
    api.getInvitations().then(setInvitations).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function invite(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setCreateError(null);
    setCreated(null);
    setCopied(false);

    try {
      setCreated(await api.createInvitation(email));
      setEmail("");
      load();
    } catch (err) {
      setCreateError(
        err instanceof ApiError && err.status === 409
          ? "There is already an account or a pending invitation for that email."
          : "Could not create the invitation."
      );
    } finally {
      setSubmitting(false);
    }
  }

  const inviteLink = (token: string) =>
    typeof window === "undefined" ? "" : `${window.location.origin}/invite/${token}`;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          {error && <p className="px-5 py-3 text-sm text-danger">{error}</p>}
          {members === null && !error && (
            <div className="space-y-2 p-5">
              {[0, 1].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-lg bg-surface-hover" />
              ))}
            </div>
          )}
          {members && members.length > 0 && (
            <ul className="divide-y divide-border">
              {members.map((member) => (
                <li key={member.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {member.name}
                    </p>
                    <p className="truncate text-xs text-muted">{member.email}</p>
                  </div>
                  <Badge tone={member.role === "Owner" ? "accent" : "neutral"}>
                    {member.role}
                  </Badge>
                  <Badge tone={member.is_active ? "success" : "neutral"}>
                    {member.is_active ? "Active" : "Inactive"}
                  </Badge>
                  {member.is_active && member.role !== "Owner" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={deactivating === member.id}
                      onClick={async () => {
                        setDeactivating(member.id);
                        try {
                          await api.deactivateUser(member.id);
                          load();
                        } catch {
                          setError("Could not deactivate that member.");
                        } finally {
                          setDeactivating(null);
                        }
                      }}
                    >
                      {deactivating === member.id ? "Removing…" : "Remove access"}
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invite someone</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <p className="mb-4 text-sm text-muted">
            New members join as Staff. You&rsquo;ll get a private joining link to send
            them however you normally get hold of your team.
          </p>

          <form onSubmit={invite} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Email" htmlFor="inviteEmail" className="flex-1">
              <Input
                id="inviteEmail"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="newstarter@example.com"
              />
            </Field>
            <Button type="submit" disabled={submitting}>
              <PlusIcon className="h-4 w-4" />
              {submitting ? "Creating…" : "Create invite"}
            </Button>
          </form>

          {createError && (
            <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {createError}
            </p>
          )}

          {created && (
            <div className="mt-4 rounded-xl border border-accent/30 bg-accent-subtle p-4">
              <p className="text-sm font-medium text-foreground">
                Joining link for {created.email}
              </p>
              <p className="mt-0.5 text-xs text-muted">
                Expires {formatDate(created.expires_at)}. Anyone with this link can join
                your workspace as Staff, so send it to them directly.
              </p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <Input
                  readOnly
                  value={inviteLink(created.token)}
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Joining link"
                  className="flex-1 text-xs"
                />
                <Button
                  variant="secondary"
                  onClick={async () => {
                    await navigator.clipboard.writeText(inviteLink(created.token));
                    setCopied(true);
                  }}
                >
                  {copied ? "Copied" : "Copy link"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invitations</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pt-2">
          {invitations?.length === 0 && (
            <EmptyState title="No invitations yet" description="Invite someone above." />
          )}
          {invitations && invitations.length > 0 && (
            <ul className="divide-y divide-border">
              {invitations.map((invitation) => (
                <li key={invitation.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {invitation.email}
                    </p>
                    <p className="truncate text-xs text-muted">
                      Invited {formatDate(invitation.created_at)} · expires{" "}
                      {formatDate(invitation.expires_at)}
                    </p>
                  </div>
                  <Badge tone={STATUS_TONE[invitation.status] ?? "neutral"}>
                    {invitation.status}
                  </Badge>
                  {invitation.status === "pending" && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={async () => {
                        await api.revokeInvitation(invitation.id);
                        load();
                      }}
                    >
                      Revoke
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
