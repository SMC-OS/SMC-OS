"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { PlusIcon } from "@/components/ui/icons";
import Link from "next/link";

import { ApiError, api } from "@/lib/api";
import type { Subscription } from "@/types/billing";
import type { InvitationCreateOut, InvitationOut } from "@/types/invitation";
import type { TeamMemberOut } from "@/types/user";

const PLAN_NAMES: Record<string, string> = {
  pro: "SIMO OS Pro",
  business: "SIMO OS Business",
  enterprise: "Enterprise",
};

const SUBSCRIPTION_STATUS_TONE: Record<string, "info" | "success" | "neutral" | "warning" | "danger"> = {
  active: "success",
  trialing: "info",
  past_due: "warning",
  unpaid: "danger",
  cancelled: "neutral",
  incomplete: "neutral",
};

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
  const { isAuthenticated, isReady, role, userId } = useAuth();

  const [invitations, setInvitations] = useState<InvitationOut[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const [teamMembers, setTeamMembers] = useState<TeamMemberOut[] | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [deactivatingId, setDeactivatingId] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createdInvite, setCreatedInvite] = useState<InvitationCreateOut | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  const [subscription, setSubscription] = useState<Subscription | null | undefined>(undefined);
  const [billingError, setBillingError] = useState<string | null>(null);
  const [billingActionLoading, setBillingActionLoading] = useState(false);

  const isOwner = role === "Owner";

  function loadSubscription() {
    api
      .getSubscription()
      .then(setSubscription)
      .catch(() => setBillingError("Could not load your subscription."));
  }

  function loadInvitations() {
    api
      .getInvitations()
      .then(setInvitations)
      .catch((err) =>
        setListError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }

  function loadTeam() {
    api
      .getUsers()
      .then(setTeamMembers)
      .catch((err) =>
        setTeamError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    if (isOwner) {
      loadInvitations();
      loadTeam();
      loadSubscription();
    }
  }, [isReady, isAuthenticated, isOwner, router]);

  if (!isReady || !isAuthenticated) return null;

  async function handleManageBilling() {
    setBillingError(null);
    setBillingActionLoading(true);
    try {
      const { portal_url } = await api.createPortalSession();
      window.location.assign(portal_url);
    } catch (err) {
      setBillingError(
        err instanceof ApiError ? err.message : "Something went wrong."
      );
    } finally {
      setBillingActionLoading(false);
    }
  }

  async function handleCancelSubscription() {
    setBillingError(null);
    setBillingActionLoading(true);
    try {
      const updated = await api.cancelSubscriptionAtPeriodEnd();
      setSubscription(updated);
    } catch (err) {
      setBillingError(
        err instanceof ApiError ? err.message : "Something went wrong."
      );
    } finally {
      setBillingActionLoading(false);
    }
  }

  async function handleResumeSubscription() {
    setBillingError(null);
    setBillingActionLoading(true);
    try {
      const updated = await api.resumeSubscription();
      setSubscription(updated);
    } catch (err) {
      setBillingError(
        err instanceof ApiError ? err.message : "Something went wrong."
      );
    } finally {
      setBillingActionLoading(false);
    }
  }

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

  async function handleDeactivate(id: string) {
    setDeactivatingId(id);
    setTeamError(null);
    try {
      await api.deactivateUser(id);
      loadTeam();
    } catch (err) {
      setTeamError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setDeactivatingId(null);
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
              <CardTitle>Team</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {teamError && <p className="p-5 text-sm text-danger">{teamError}</p>}
              {teamMembers === null && !teamError && (
                <p className="p-5 text-center text-sm text-muted">Loading…</p>
              )}
              {teamMembers && teamMembers.length > 0 && (
                <ul className="divide-y divide-border">
                  {teamMembers.map((member) => (
                    <li key={member.id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {member.name}
                        </p>
                        <p className="truncate text-xs text-muted">{member.email}</p>
                      </div>
                      <Badge tone="neutral">{member.role}</Badge>
                      <Badge tone={member.is_active ? "success" : "neutral"}>
                        {member.is_active ? "active" : "inactive"}
                      </Badge>
                      {member.is_active && member.id !== userId && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={deactivatingId === member.id}
                          onClick={() => handleDeactivate(member.id)}
                        >
                          {deactivatingId === member.id ? "Deactivating…" : "Deactivate"}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Billing</CardTitle>
              <Link href="/pricing" className="text-xs text-accent hover:underline">
                View plans
              </Link>
            </CardHeader>
            <CardContent className="pt-4">
              {billingError && (
                <p className="mb-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                  {billingError}
                </p>
              )}

              {subscription === undefined && (
                <p className="text-sm text-muted">Loading…</p>
              )}

              {subscription === null && (
                <div className="flex items-center justify-between">
                  <p className="text-sm text-muted">
                    No active subscription yet.
                  </p>
                  <Link href="/pricing">
                    <Button type="button" size="sm">
                      Choose a plan
                    </Button>
                  </Link>
                </div>
              )}

              {subscription && (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        {PLAN_NAMES[subscription.plan] ?? subscription.plan}
                      </p>
                      <p className="text-xs text-muted">
                        Billed {subscription.billing_period}
                        {subscription.current_period_end &&
                          ` · Renews ${new Date(subscription.current_period_end).toLocaleDateString()}`}
                      </p>
                    </div>
                    <Badge tone={SUBSCRIPTION_STATUS_TONE[subscription.status] ?? "neutral"}>
                      {subscription.status.replace("_", " ")}
                    </Badge>
                  </div>

                  {subscription.cancel_at_period_end && (
                    <p className="rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
                      Cancels at the end of the current billing period.
                    </p>
                  )}

                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={billingActionLoading}
                      onClick={handleManageBilling}
                    >
                      Manage billing
                    </Button>
                    {subscription.cancel_at_period_end ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={billingActionLoading}
                        onClick={handleResumeSubscription}
                      >
                        Resume
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={billingActionLoading}
                        onClick={handleCancelSubscription}
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

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
