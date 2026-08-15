"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";
import type { PortalLinkCreateOut, PortalLinkOut } from "@/types/portal";

const PORTAL_LINK_STATUS_TONE: Record<string, "success" | "neutral" | "warning"> = {
  active: "success",
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

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sprint 013 — share a read-only client portal link. Any authenticated
  // tenant user can generate one (not Owner-only, unlike team invites).
  const [creatingLink, setCreatingLink] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [createdLink, setCreatedLink] = useState<PortalLinkCreateOut | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  // Sprint 014 — existing links, so staff can see and revoke what's
  // already been shared. GET/DELETE /portal-links existed since Sprint
  // 013 but had no frontend consumer until now.
  const [portalLinks, setPortalLinks] = useState<PortalLinkOut[] | null>(null);
  const [linksError, setLinksError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  function loadPortalLinks(customerId: string) {
    setLinksError(null);
    api
      .getPortalLinks(customerId)
      .then(setPortalLinks)
      .catch((err) =>
        setLinksError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getCustomer(params.id)
      .then((c) => {
        setCustomer(c);
        loadPortalLinks(c.id);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Customer not found."
            : "Something went wrong."
        )
      );
  }, [isReady, isAuthenticated, router, params.id]);

  if (!isReady || !isAuthenticated) return null;

  function portalLink(token: string): string {
    return `${window.location.origin}/portal/${token}`;
  }

  async function handleCreatePortalLink() {
    if (!customer) return;
    setCreatingLink(true);
    setLinkError(null);
    setLinkCopied(false);

    try {
      const link = await api.createPortalLink(customer.id);
      setCreatedLink(link);
      loadPortalLinks(customer.id);
    } catch (err) {
      setLinkError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setCreatingLink(false);
    }
  }

  async function handleCopyPortalLink() {
    if (!createdLink) return;
    await navigator.clipboard.writeText(portalLink(createdLink.token));
    setLinkCopied(true);
  }

  async function handleRevokePortalLink(id: string) {
    if (!customer) return;
    setRevokingId(id);
    setLinksError(null);

    try {
      await api.revokePortalLink(id);
      loadPortalLinks(customer.id);
    } catch (err) {
      setLinksError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <Link href="/customers" className="text-sm text-muted hover:text-foreground">
          &larr; Customers
        </Link>
      </div>

      {error && (
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {!error && !customer && (
        <p className="text-sm text-muted">Loading…</p>
      )}

      {customer && (
        <Card>
          <CardContent>
            <div className="flex items-center gap-3">
              <Avatar name={customer.name} className="h-12 w-12 text-base" />
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-foreground">
                  {customer.name}
                </h1>
                <p className="text-xs text-muted">
                  Added {formatRelativeTime(customer.created_at)}
                </p>
              </div>
            </div>

            <dl className="mt-6 space-y-3 border-t border-border pt-4">
              <div>
                <dt className="text-xs font-medium text-muted">Email</dt>
                <dd className="text-sm text-foreground">
                  {customer.email ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted">Phone</dt>
                <dd className="text-sm text-foreground">
                  {customer.phone ?? "—"}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      )}

      {customer && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Client portal</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-muted">
              Share a read-only link so {customer.name} can check the status of
              their own projects and quotes — no account needed.
            </p>
            <Button type="button" onClick={handleCreatePortalLink} disabled={creatingLink}>
              {creatingLink ? "Generating…" : "Generate portal link"}
            </Button>

            {linkError && (
              <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                {linkError}
              </p>
            )}

            {createdLink && (
              <div className="mt-4 rounded-lg border border-border bg-background p-3">
                <p className="text-sm text-foreground">
                  Portal link created. It expires {formatDate(createdLink.expires_at)}.
                </p>
                <div className="mt-2 flex items-center gap-2">
                  <Input
                    readOnly
                    value={portalLink(createdLink.token)}
                    onFocus={(e) => e.currentTarget.select()}
                    className="flex-1 text-xs"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={handleCopyPortalLink}
                  >
                    {linkCopied ? "Copied" : "Copy link"}
                  </Button>
                </div>
              </div>
            )}

            {linksError && (
              <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
                {linksError}
              </p>
            )}

            {!linksError && portalLinks && portalLinks.length > 0 && (
              <div className="mt-4 border-t border-border pt-4">
                <p className="mb-2 text-xs font-medium text-muted">
                  Links can only be copied when first created — this list is for
                  checking status and revoking, not retrieving the URL again.
                </p>
                <ul className="divide-y divide-border">
                  {portalLinks.map((link) => (
                    <li key={link.id} className="flex items-center gap-3 py-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-muted">
                          Created {formatDate(link.created_at)} · Expires{" "}
                          {formatDate(link.expires_at)}
                        </p>
                      </div>
                      <Badge tone={PORTAL_LINK_STATUS_TONE[link.status] ?? "neutral"}>
                        {link.status}
                      </Badge>
                      {link.status === "active" && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={revokingId === link.id}
                          onClick={() => handleRevokePortalLink(link.id)}
                        >
                          {revokingId === link.id ? "Revoking…" : "Revoke"}
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
