"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { ApiError, api } from "@/lib/api";
import { PROJECT_STATUS_LABEL, PROJECT_STATUS_TONE } from "@/lib/projects";
import { formatRelativeTime } from "@/lib/utils";
import { PROJECT_STATUSES } from "@/types/project";
import type { Customer } from "@/types/customer";
import type { Project } from "@/types/project";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAuthenticated, isReady, role } = useAuth();
  const [project, setProject] = useState<Project | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);

  // Sprint 021 — enquiry-to-customer conversion (docs/SPRINTS/sprint-021.md).
  const [showConvertForm, setShowConvertForm] = useState(false);
  const [convertName, setConvertName] = useState("");
  const [convertEmail, setConvertEmail] = useState("");
  const [convertPhone, setConvertPhone] = useState("");
  const [converting, setConverting] = useState(false);

  function load() {
    api
      .getProject(params.id)
      .then((p) => {
        setProject(p);
        if (p.customer_id) {
          api.getCustomer(p.customer_id).then(setCustomer).catch(() => {});
        }
      })
      .catch((err) =>
        setError(
          err instanceof ApiError && err.status === 404
            ? "Project not found."
            : "Something went wrong."
        )
      );
  }

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, isAuthenticated, params.id]);

  if (!isReady || !isAuthenticated) return null;

  const currentIndex = project ? PROJECT_STATUSES.indexOf(project.status) : -1;
  const nextStatus =
    currentIndex >= 0 && currentIndex < PROJECT_STATUSES.length - 1
      ? PROJECT_STATUSES[currentIndex + 1]
      : null;

  async function handleAdvance() {
    if (!project || !nextStatus) return;
    setAdvancing(true);
    try {
      const updated = await api.updateProjectStatus(project.id, nextStatus);
      setProject(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setAdvancing(false);
    }
  }

  const canConvert = role === "Owner" || role === "Staff";
  const showConvertAction =
    !!project && project.status === "enquiry" && project.customer_id == null && canConvert;

  async function handleConvert(e: React.FormEvent) {
    e.preventDefault();
    if (!project) return;
    setConverting(true);
    try {
      const convertedCustomer = await api.convertProjectToCustomer(project.id, {
        name: convertName,
        email: convertEmail || null,
        phone: convertPhone || null,
      });
      // The server's returned Customer is authoritative — applied only
      // after a successful response, never optimistically.
      setCustomer(convertedCustomer);
      setProject({ ...project, customer_id: convertedCustomer.id });
      setShowConvertForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setConverting(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <div className="mb-6">
        <Link href="/projects" className="text-sm text-muted hover:text-foreground">
          &larr; Projects
        </Link>
      </div>

      {error && (
        <Card>
          <CardContent>
            <p className="text-sm text-danger">{error}</p>
          </CardContent>
        </Card>
      )}

      {!error && !project && <p className="text-sm text-muted">Loading…</p>}

      {project && (
        <Card>
          <CardContent>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-foreground">
                  {project.name}
                </h1>
                <p className="text-xs text-muted">
                  Started {formatRelativeTime(project.created_at)}
                </p>
              </div>
              <Badge tone={PROJECT_STATUS_TONE[project.status]}>
                {PROJECT_STATUS_LABEL[project.status]}
              </Badge>
            </div>

            <dl className="mt-6 space-y-3 border-t border-border pt-4">
              <div>
                <dt className="text-xs font-medium text-muted">Customer</dt>
                <dd className="text-sm text-foreground">
                  {customer ? (
                    <Link
                      href={`/customers/${customer.id}`}
                      className="text-accent hover:underline"
                    >
                      {customer.name}
                    </Link>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted">Notes</dt>
                <dd className="text-sm text-foreground">{project.notes ?? "—"}</dd>
              </div>
            </dl>

            <div className="mt-6 border-t border-border pt-4">
              {nextStatus ? (
                <Button onClick={handleAdvance} disabled={advancing}>
                  {advancing
                    ? "Advancing…"
                    : `Advance to ${PROJECT_STATUS_LABEL[nextStatus]}`}
                </Button>
              ) : (
                <p className="text-sm text-muted">
                  This project has completed the pipeline.
                </p>
              )}
            </div>

            {showConvertAction && (
              <div className="mt-6 border-t border-border pt-4">
                {showConvertForm ? (
                  <form onSubmit={handleConvert} className="flex flex-col gap-4">
                    <Field label="Full name" htmlFor="convert-name">
                      <Input
                        id="convert-name"
                        required
                        value={convertName}
                        onChange={(e) => setConvertName(e.target.value)}
                        placeholder="e.g. James Okafor"
                      />
                    </Field>
                    <Field label="Email" htmlFor="convert-email">
                      <Input
                        id="convert-email"
                        type="email"
                        value={convertEmail}
                        onChange={(e) => setConvertEmail(e.target.value)}
                        placeholder="james@example.com"
                      />
                    </Field>
                    <Field label="Phone" htmlFor="convert-phone">
                      <Input
                        id="convert-phone"
                        value={convertPhone}
                        onChange={(e) => setConvertPhone(e.target.value)}
                        placeholder="07123 456789"
                      />
                    </Field>
                    <Button type="submit" disabled={converting}>
                      {converting ? "Saving…" : "Save customer"}
                    </Button>
                  </form>
                ) : (
                  <Button onClick={() => setShowConvertForm(true)} variant="outline">
                    Convert to Customer
                  </Button>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
