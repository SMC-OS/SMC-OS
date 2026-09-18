"use client";

import { useState } from "react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent } from "@/components/ui/Card";
import { EditIcon } from "@/components/ui/icons";
import { cn, formatRelativeTime } from "@/lib/utils";
import { WORKFLOW_ROLE_LABELS, WORKFLOW_ROLE_TONE } from "@/types/workflow";
import type { Project } from "@/types/project";

export interface Project360Tab {
  key: string;
  label: string;
  content: ReactNode;
}

/**
 * GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — the persistent
 * Project 360 header (real data only: name, trade, current workflow
 * stage, started-when — nothing here is fabricated or placeholder) plus
 * the tab bar. Tabs are switched by conditional render, not CSS hiding,
 * so an inactive tab's content — and any fetch it would otherwise
 * trigger — genuinely isn't mounted, matching every other lazy panel in
 * this app (ProjectTasksPanel included).
 */
export function Project360Shell({
  project,
  tradeLabel,
  onEdit,
  tabs,
}: {
  project: Project;
  tradeLabel: string | null;
  onEdit: () => void;
  tabs: Project360Tab[];
}) {
  const [activeKey, setActiveKey] = useState(tabs[0]?.key);
  const active = tabs.find((tab) => tab.key === activeKey) ?? tabs[0];

  return (
    <div>
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
                {project.name}
              </h1>
              <p className="text-xs text-muted">
                {tradeLabel ? `${tradeLabel} · ` : ""}
                Started {formatRelativeTime(project.created_at)}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge tone={WORKFLOW_ROLE_TONE[project.workflow.role]}>
                {WORKFLOW_ROLE_LABELS[project.workflow.role]}
              </Badge>
              <span className="hidden text-sm text-muted sm:inline">
                {project.workflow.stage_label}
              </span>
              <Button variant="outline" size="sm" onClick={onEdit}>
                <EditIcon className="h-4 w-4" />
                Edit
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div
        role="tablist"
        aria-label="Project sections"
        className="mt-4 flex gap-2 overflow-x-auto pb-1"
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active?.key === tab.key}
            onClick={() => setActiveKey(tab.key)}
            className={cn(
              "shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
              active?.key === tab.key
                ? "border-accent bg-accent text-accent-foreground"
                : "border-border text-muted hover:border-border-strong hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="mt-4">
        {active?.content}
      </div>
    </div>
  );
}
