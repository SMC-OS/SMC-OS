import { EmptyState } from "@/components/ui/Card";
import { ArrowRightIcon } from "@/components/ui/icons";
import { formatDateTime } from "@/lib/utils";
import type { WorkflowHistoryEntry } from "@/types/workflow";

/**
 * GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — the Timeline tab's
 * content: the append-only audit trail GET /projects/{id}/workflow/history
 * returns, oldest first (the order the backend already sorts it in).
 */
export function WorkflowHistory({ history }: { history: WorkflowHistoryEntry[] }) {
  if (history.length === 0) {
    return (
      <EmptyState
        title="No workflow moves yet"
        description="Every stage change, Hold, Resume and Cancel for this project will appear here."
      />
    );
  }

  return (
    <ul className="space-y-3">
      {history.map((entry) => (
        <li
          key={entry.id}
          className="flex items-start justify-between gap-3 rounded-md border border-border p-3"
        >
          <div className="flex items-center gap-2 text-sm text-foreground">
            <span>{entry.from_stage_label ?? "—"}</span>
            <ArrowRightIcon className="h-3.5 w-3.5 shrink-0 text-muted" />
            <span className="font-medium">{entry.to_stage_label}</span>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-xs text-muted">{formatDateTime(entry.created_at)}</p>
            {entry.reason && <p className="text-xs text-muted">{entry.reason}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
