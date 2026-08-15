"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import type { InvitationCreateOut, InvitationOut } from "@/types/invitation";

const STATUS_TONE: Record<string, "info" | "success" | "neutral" | "warning"> = {
  pending: "info",
  accepted: "success",
  revoked: "neutral",
  expired: "warning",
};

function formatDate(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function SettingsPage() {
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useAuth();

  const [invitations, setInvitations] = useState<InvitationOut[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdInvite, setCreatedInvite] = useState<InvitationCreateOut | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  const isOwner = role === "Owner";

  function loadInvitations() {
    api
      .getInvitations()
      .then(setInvitations)
      .catch((err) =>
        setListError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    if (isOwner) loadInvitations();
  }, [isReady, isAuthenticated, isOwner, router]);

  if (!isReady || !isAuthenticated) return null;

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setCreateError(null);
    setCreatedInvite(null);
    setLinkCopied(false);

    try {
      const invite = await api.createInvitation(email);
      setCreatedInvite(invite);
      setEmail("");
      loadInvitations();
    } catch (err) {
      setCreateError(
        err instanceof ApiError && err.status === 409
          ? "An invitation or account for that email already exists."
          : "Something went wrong."
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRevoke(id: string) {
    try {
      await api.revokeInvitation(id);
      loadInvitations();
    } catch (err) {
      setListError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  function inviteLink(token: string): string {
    return `${window.location.origin}/invite/${token}`;
  }

  async function handleCopyLink() {
    if (!createdInvite) return;
    await navigator.clipboard.writeText(inviteLink(createdInvite.token));
    setLinkCopied(true);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Settings
        </h1>
        <p className="mt-1 text-sm text-muted">
          Account, team, and workspace settings.
        </p>
      </div>

      {!isOwner && (
        <Card>
          <CardContent>
            <p className="text-sm text-muted">
              Only workspace owners can invite and manage teammates.
            </p>
          </CardContent>
        </Card>
      )}

      {isOwner && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Invite a teammate</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-4 text-sm text-muted">
                Invites join as Staff in this workspace. There&apos;s no email
                delivery yet — copy the generated link and send it yourself.
              </p>
              <form onSubmit={handleInvite} className="flex items-end gap-3">
                <Field label="Email" htmlFor="inviteEmail" className="flex-1">
                  <Input
                    id="inviteEmail"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="newhire@example.com"
                  />
                </Field>
                <Button type="submit" disabled={submitting}>
                  <PlusIcon className="h-4 w-4" />
                  {submitting ? "Sending…" : "Send invite"}
                </Button>
              </form>

              {createError && (
                <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                  {createError}
                </p>
              )}

              {createdInvite && (
                <div className="mt-4 rounded-lg border border-border bg-background p-3">
                  <p className="text-sm text-foreground">
                    Invitation created for{" "}
                    <span className="font-medium">{createdInvite.email}</span>.
                    Share this link — it expires{" "}
                    {formatDate(createdInvite.expires_at)}.
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <Input
                      readOnly
                      value={inviteLink(createdInvite.token)}
                      onFocus={(e) => e.currentTarget.select()}
                      className="flex-1 text-xs"
                    />
                    <Button type="button" variant="secondary" size="sm" onClick={handleCopyLink}>
                      {linkCopied ? "Copied" : "Copy link"}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Pending &amp; past invitations</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {listError && <p className="p-5 text-sm text-danger">{listError}</p>}
              {!listError && invitations === null && (
                <p className="p-5 text-center text-sm text-muted">Loading…</p>
              )}
              {!listError && invitations?.length === 0 && (
                <p className="p-5 text-center text-sm text-muted">
                  No invitations yet — send one above.
                </p>
              )}
              {invitations && invitations.length > 0 && (
                <ul className="divide-y divide-border">
                  {invitations.map((invite) => (
                    <li
                      key={invite.id}
                      className="flex items-center gap-3 px-5 py-3"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {invite.email}
                        </p>
                        <p className="truncate text-xs text-muted">
                          Invited {formatDate(invite.created_at)} · Expires{" "}
                          {formatDate(invite.expires_at)}
                        </p>
                      </div>
                      <Badge tone={STATUS_TONE[invite.status] ?? "neutral"}>
                        {invite.status}
                      </Badge>
                      {invite.status === "pending" && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleRevoke(invite.id)}
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
      )}
    </div>
  );
}
