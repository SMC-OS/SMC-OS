import { AlertCircleIcon } from "@/components/ui/icons";
import type { GateBlocker } from "@/types/workflow";

/**
 * GeoCore Premium OS Plan 01 (Sprint 040, Task 8). Renders exactly what
 * the backend's own GateBlocker list says — never a generic "can't do
 * that" — so the reason a stage isn't reachable yet is always visible,
 * never guessed at by the frontend.
 */
export function WorkflowBlockers({ blockers }: { blockers: GateBlocker[] }) {
  if (blockers.length === 0) return null;

  return (
    <ul className="mt-1.5 space-y-1">
      {blockers.map((blocker) => (
        <li
          key={blocker.code}
          className="flex items-start gap-1.5 text-xs text-muted"
        >
          <AlertCircleIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{blocker.message}</span>
        </li>
      ))}
    </ul>
  );
}
