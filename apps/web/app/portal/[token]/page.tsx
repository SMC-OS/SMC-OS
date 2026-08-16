"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { PROJECT_STATUS_LABEL, PROJECT_STATUS_TONE } from "@/lib/projects";
import { formatCurrencyGBP } from "@/lib/utils";
import type { DocumentOut } from "@/types/document";
import type { PortalPublicOut } from "@/types/portal";
import type { ProjectStatus } from "@/types/project";

const UNUSABLE_MESSAGES: Record<string, string> = {
  revoked: "This link has been revoked. Contact us for a new one.",
  expired: "This link has expired. Contact us for a new one.",
};

function formatDate(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function ClientPortalPage() {
  const params = useParams<{ token: string }>();

  const [portal, setPortal] = useState<PortalPublicOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Sprint 016 — documents are a separate endpoint, not bundled into
  // PortalPublicOut, so they get their own state and fetch.
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [downloadingDocId, setDownloadingDocId] = useState<string | null>(null);

  async function handleDownloadInvoice(quoteId: string) {
    setDownloadingId(quoteId);
    setDownloadError(null);
    try {
      await api.downloadPortalInvoice(params.token, quoteId);
    } catch {
      setDownloadError("Could not download that invoice. Try again.");
    } finally {
      setDownloadingId(null);
    }
  }

  async function handleDownloadDocument(doc: DocumentOut) {
    setDownloadingDocId(doc.id);
    setDocumentsError(null);
    try {
      await api.downloadPortalDocument(params.token, doc.id, doc.original_filename);
    } catch {
      setDocumentsError("Could not download that document. Try again.");
    } finally {
      setDownloadingDocId(null);
    }
  }

  useEffect(() => {
    api
      .getPortalByToken(params.token)
      .then(setPortal)
      .catch((err) =>
        setLoadError(
          err instanceof ApiError && err.status === 404
            ? "This link isn't valid."
            : "Something went wrong."
        )
      );
    api
      .getPortalDocuments(params.token)
      .then(setDocuments)
      .catch((err) =>
        setDocumentsError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [params.token]);

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Your projects
        </h1>
        {portal && portal.status === "active" && (
          <p className="mt-1 text-sm text-muted">
            <span className="font-medium text-foreground">{portal.tenant_name}</span> —{" "}
            {portal.customer_name}
          </p>
        )}
      </div>

      {loadError && (
        <Card>
          <CardContent>
            <p className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
              {loadError}
            </p>
          </CardContent>
        </Card>
      )}

      {!loadError && portal === null && (
        <Card>
          <CardContent>
            <p className="text-center text-sm text-muted">Loading…</p>
          </CardContent>
        </Card>
      )}

      {!loadError && portal && portal.status !== "active" && (
        <Card>
          <CardContent>
            <p className="rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
              {UNUSABLE_MESSAGES[portal.status] ?? "This link can no longer be used."}
            </p>
          </CardContent>
        </Card>
      )}

      {!loadError && portal && portal.status === "active" && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Projects</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {portal.projects.length === 0 && (
                <p className="p-5 text-center text-sm text-muted">No projects yet.</p>
              )}
              {portal.projects.length > 0 && (
                <ul className="divide-y divide-border">
                  {portal.projects.map((project) => (
                    <li key={project.id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {project.name}
                        </p>
                        <p className="truncate text-xs text-muted">
                          Started {formatDate(project.created_at)}
                        </p>
                      </div>
                      <Badge tone={PROJECT_STATUS_TONE[project.status as ProjectStatus] ?? "neutral"}>
                        {PROJECT_STATUS_LABEL[project.status as ProjectStatus] ?? project.status}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Quotes</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {portal.quotes.length === 0 && (
                <p className="p-5 text-center text-sm text-muted">No quotes yet.</p>
              )}
              {portal.quotes.length > 0 && (
                <ul className="divide-y divide-border">
                  {portal.quotes.map((quote) => (
                    <li key={quote.id} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {quote.material} — {quote.thickness}
                        </p>
                        <p className="truncate text-xs text-muted">
                          Quoted {formatDate(quote.created_at)}
                        </p>
                      </div>
                      <p className="text-sm font-semibold text-foreground">
                        {formatCurrencyGBP(quote.total)}
                      </p>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => handleDownloadInvoice(quote.id)}
                        disabled={downloadingId === quote.id}
                      >
                        {downloadingId === quote.id ? "Downloading…" : "Invoice"}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              {downloadError && (
                <p className="px-5 pb-3 text-sm text-danger">{downloadError}</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {documentsError && (
                <p className="p-5 text-sm text-danger">{documentsError}</p>
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
                          {formatDate(doc.created_at)}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => handleDownloadDocument(doc)}
                        disabled={downloadingDocId === doc.id}
                      >
                        {downloadingDocId === doc.id ? "Downloading…" : "Download"}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <p className="text-center text-xs text-muted">
            This link expires {formatDate(portal.expires_at)}.
          </p>
        </div>
      )}
    </div>
  );
}
