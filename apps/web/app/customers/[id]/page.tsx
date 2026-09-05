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
import { EditIcon } from "@/components/ui/icons";
import { CustomerContextPanel } from "@/components/customers/CustomerContextPanel";
import { CustomerForm } from "@/components/customers/CustomerForm";
import { usePolling } from "@/hooks/usePolling";
import { ApiError, api } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import type { Customer } from "@/types/customer";
import type { DocumentOut } from "@/types/document";
import type { MessageOut } from "@/types/message";
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
  const { isAuthenticated, isReady, userId } = useAuth();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Sprint 036 (Workstream D) — inline edit, reusing the same form the
  // create page uses so the two cannot drift into asking for different
  // things.
  const [editing, setEditing] = useState(false);

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

  // Sprint 016 — client-portal documents. Customer-level, not
  // project-level, matching PortalLink's precedent.
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloadingDocId, setDownloadingDocId] = useState<string | null>(null);

  function loadDocuments(customerId: string) {
    setDocumentsError(null);
    api
      .getDocuments(customerId)
      .then(setDocuments)
      .catch((err) =>
        setDocumentsError(err instanceof ApiError ? err.message : "Something went wrong.")
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
        loadDocuments(c.id);
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Customer not found."
            : "Something went wrong."
        )
      );
  }, [isReady, isAuthenticated, router, params.id]);

  // Sprint 017 (ADR-033) — two-way messaging on the customer's portal
  // thread. Polled via the shared usePolling hook (ADR-004), same
  // mechanism every other live panel uses — not a new pattern. Declared
  // above the early return below so hook order stays stable regardless
  // of auth state (rules-of-hooks).
  const {
    data: messages,
    error: messagesError,
    refetch: refetchMessages,
  } = usePolling<MessageOut[]>(
    () => (customer ? api.getMessages(customer.id) : Promise.resolve([])),
    { enabled: Boolean(customer) }
  );
  const [messageBody, setMessageBody] = useState("");
  const [sendingMessage, setSendingMessage] = useState(false);
  const [sendMessageError, setSendMessageError] = useState<string | null>(null);

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

  async function handleUploadDocument(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !customer) return;
    setUploading(true);
    setDocumentsError(null);
    try {
      await api.uploadDocument(customer.id, file);
      loadDocuments(customer.id);
    } catch (err) {
      setDocumentsError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleDownloadDocument(doc: DocumentOut) {
    setDownloadingDocId(doc.id);
    try {
      await api.downloadDocument(doc.id, doc.original_filename);
    } catch (err) {
      setDocumentsError(err instanceof ApiError ? err.message : "Download failed.");
    } finally {
      setDownloadingDocId(null);
    }
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatMessageTime(isoTimestamp: string): string {
    return new Date(isoTimestamp).toLocaleString(undefined, {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!customer) return;
    if (!messageBody.trim()) return;

    setSendingMessage(true);
    setSendMessageError(null);
    try {
      await api.postMessage(customer.id, messageBody);
      setMessageBody("");
      await refetchMessages();
    } catch (err) {
      setSendMessageError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSendingMessage(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
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

      {customer && !editing && (
        <Card>
          <CardContent>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <Avatar
                  name={customer.company_name || customer.name}
                  className="h-12 w-12 text-base"
                />
                <div className="min-w-0">
                  <h1 className="truncate text-xl font-semibold tracking-tight text-foreground">
                    {customer.company_name || customer.name}
                  </h1>
                  <p className="text-xs text-muted">
                    {customer.company_name ? `${customer.name} · ` : ""}
                    Added {formatRelativeTime(customer.created_at)}
                  </p>
                </div>
              </div>

              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <EditIcon className="h-4 w-4" />
                Edit
              </Button>
            </div>

            {/* Sprint 036 (Workstream D) — a construction customer record.
                Every field renders as an em dash when absent rather than
                being hidden, so the page shows what is missing as clearly
                as what is present: an address you do not have is
                information. */}
            <dl className="mt-6 grid grid-cols-1 gap-4 border-t border-border pt-4 sm:grid-cols-2">
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted">Email</dt>
                <dd className="truncate text-sm text-foreground">
                  {customer.email ? (
                    <a href={`mailto:${customer.email}`} className="hover:underline">
                      {customer.email}
                    </a>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div className="min-w-0">
                <dt className="text-xs font-medium text-muted">Phone</dt>
                <dd className="truncate text-sm text-foreground">
                  {customer.phone ? (
                    <a href={`tel:${customer.phone}`} className="hover:underline">
                      {customer.phone}
                    </a>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div className="min-w-0 sm:col-span-2">
                <dt className="text-xs font-medium text-muted">Address</dt>
                <dd className="text-sm text-foreground">
                  {[
                    customer.address_line1,
                    customer.address_line2,
                    customer.city,
                    customer.postcode,
                  ]
                    .filter(Boolean)
                    .join(", ") || "—"}
                </dd>
              </div>
              {customer.notes && (
                <div className="min-w-0 sm:col-span-2">
                  <dt className="text-xs font-medium text-muted">Notes</dt>
                  <dd className="whitespace-pre-wrap text-sm text-foreground">
                    {customer.notes}
                  </dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>
      )}

      {customer && editing && (
        <div>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Edit customer
            </h1>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
          <CustomerForm
            initial={customer}
            submitLabel="Save changes"
            onSubmit={async (values) => {
              const updated = await api.updateCustomer(customer.id, values);
              setCustomer(updated);
              setEditing(false);
            }}
          />
        </div>
      )}

      {customer && !editing && <CustomerContextPanel customerId={customer.id} />}

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

            {portalLinks && portalLinks.length > 0 && (
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

      {customer && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Documents</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="border-b border-border p-5">
              <label className="flex items-center gap-3">
                <span className="text-sm text-muted">
                  {uploading ? "Uploading…" : "Upload a document"}
                </span>
                <input
                  type="file"
                  onChange={handleUploadDocument}
                  disabled={uploading}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.jpg,.jpeg,.png,.heic,.webp"
                  className="text-sm text-foreground"
                />
              </label>
            </div>
            {documentsError && (
              <p className="p-5 text-sm text-danger">{documentsError}</p>
            )}
            {documents === null && !documentsError && (
              <p className="p-5 text-center text-sm text-muted">Loading…</p>
            )}
            {documents && documents.length === 0 && (
              <p className="p-5 text-center text-sm text-muted">No documents yet.</p>
            )}
            {documents && documents.length > 0 && (
              <ul className="divide-y divide-border">
                {documents.map((doc) => (
                  <li key={doc.id} className="flex items-center gap-3 px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {doc.original_filename}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {formatFileSize(doc.size_bytes)} · {formatDate(doc.created_at)}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={downloadingDocId === doc.id}
                      onClick={() => handleDownloadDocument(doc)}
                    >
                      {downloadingDocId === doc.id ? "Downloading…" : "Download"}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {customer && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Messages</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {messagesError && (
              <p className="p-5 text-sm text-danger">{messagesError}</p>
            )}
            {messages === null && !messagesError && (
              <p className="p-5 text-center text-sm text-muted">Loading…</p>
            )}
            {messages && messages.length === 0 && (
              <p className="p-5 text-center text-sm text-muted">No messages yet.</p>
            )}
            {messages && messages.length > 0 && (
              <ul className="max-h-96 space-y-3 overflow-y-auto p-5">
                {messages.map((message) => (
                  <li
                    key={message.id}
                    className={
                      message.sender_type === "staff"
                        ? "ml-auto max-w-[80%] rounded-lg bg-accent/10 px-3 py-2"
                        : "mr-auto max-w-[80%] rounded-lg bg-muted/10 px-3 py-2"
                    }
                  >
                    <p className="whitespace-pre-wrap text-sm text-foreground">
                      {message.body}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {message.sender_type === "customer"
                        ? customer.name
                        : message.sender_user_id === userId
                          ? "You"
                          : "Staff"} ·{" "}
                      {formatMessageTime(message.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            <form
              onSubmit={handleSendMessage}
              className="flex items-end gap-2 border-t border-border p-5"
            >
              <textarea
                value={messageBody}
                onChange={(e) => setMessageBody(e.target.value)}
                placeholder="Write a message…"
                rows={2}
                maxLength={5000}
                disabled={sendingMessage}
                className="h-16 flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent"
              />
              <Button type="submit" disabled={sendingMessage || !messageBody.trim()}>
                {sendingMessage ? "Sending…" : "Send"}
              </Button>
            </form>
            {sendMessageError && (
              <p className="px-5 pb-4 text-sm text-danger">{sendMessageError}</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
