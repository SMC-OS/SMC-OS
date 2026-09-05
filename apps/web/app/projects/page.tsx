"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, EmptyState } from "@/components/ui/Card";
import { CalendarIcon, FolderIcon, MapPinIcon, PlusIcon } from "@/components/ui/icons";
import { ApiError, api } from "@/lib/api";
import { PROJECT_STATUS_LABEL, PROJECT_STATUS_TONE } from "@/lib/projects";
import { cn, formatCurrency, formatDate, formatRelativeTime } from "@/lib/utils";
import { PROJECT_STATUSES, type Project, type ProjectStatus } from "@/types/project";

export default function ProjectsPage() {
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();
  const { currency } = useWorkspace();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<ProjectStatus | "live" | "all">("live");

  useEffect(() => {
    if (!isReady) return;
    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }
    api
      .getProjects(200)
      .then(setProjects)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Something went wrong.")
      );
  }, [isReady, isAuthenticated, router]);

  const filtered = useMemo(() => {
    if (!projects) return null;
    if (filter === "all") return projects;
    // "Live" is the default view because a completed job is history and a
    // list dominated by history is a list nobody scans.
    if (filter === "live") return projects.filter((p) => p.status !== "complete");
    return projects.filter((project) => project.status === filter);
  }, [projects, filter]);

  if (!isReady || !isAuthenticated) return null;

  const filters: Array<{ key: ProjectStatus | "live" | "all"; label: string }> = [
    { key: "live", label: "Live" },
    { key: "all", label: "All" },
    ...PROJECT_STATUSES.map((status) => ({
      key: status,
      label: PROJECT_STATUS_LABEL[status],
    })),
  ];

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            Projects
          </h1>
          <p className="mt-1 text-sm text-muted">
            Every job you have on, from first enquiry to completion.
          </p>
        </div>
        <Link href="/projects/new">
          <Button size="lg">
            <PlusIcon className="h-4 w-4" />
            New project
          </Button>
        </Link>
      </div>

      {projects && projects.length > 0 && (
        <div
          role="tablist"
          aria-label="Filter projects by stage"
          className="mb-4 flex gap-2 overflow-x-auto pb-1"
        >
          {filters.map((option) => (
            <button
              key={option.key}
              type="button"
              role="tab"
              aria-selected={filter === option.key}
              onClick={() => setFilter(option.key)}
              className={cn(
                "shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
                filter === option.key
                  ? "border-accent bg-accent text-accent-foreground"
                  : "border-border text-muted hover:border-border-strong hover:text-foreground"
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          {error && <p className="p-5 text-sm text-danger">{error}</p>}

          {!error && projects === null && (
            <div className="space-y-2 p-5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg bg-surface-hover" />
              ))}
            </div>
          )}

          {!error && projects?.length === 0 && (
            <EmptyState
              title="No projects yet"
              description="Approving a quote creates a project automatically, or add one directly for work that didn't start as a quote."
              action={
                <Link href="/projects/new">
                  <Button>Add a project</Button>
                </Link>
              }
            />
          )}

          {filtered?.length === 0 && projects && projects.length > 0 && (
            <EmptyState title="Nothing at this stage" />
          )}

          {filtered && filtered.length > 0 && (
            <ul className="divide-y divide-border">
              {filtered.map((project) => (
                <li key={project.id}>
                  <Link
                    href={`/projects/${project.id}`}
                    className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-hover sm:px-5"
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
                      <FolderIcon className="h-4 w-4" />
                    </div>

                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {project.name}
                      </p>
                      <p className="flex items-center gap-2 truncate text-xs text-muted">
                        {project.start_date ? (
                          <>
                            <CalendarIcon className="h-3.5 w-3.5 shrink-0" />
                            Starts {formatDate(project.start_date)}
                          </>
                        ) : (
                          <>Added {formatRelativeTime(project.created_at)}</>
                        )}
                        {project.site_city && (
                          <>
                            <MapPinIcon className="h-3.5 w-3.5 shrink-0" />
                            {project.site_city}
                          </>
                        )}
                      </p>
                    </div>

                    {project.estimated_value != null && (
                      <span className="hidden shrink-0 text-sm font-medium text-foreground sm:block">
                        {formatCurrency(project.estimated_value, currency)}
                      </span>
                    )}

                    <Badge tone={PROJECT_STATUS_TONE[project.status]}>
                      {PROJECT_STATUS_LABEL[project.status]}
                    </Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
