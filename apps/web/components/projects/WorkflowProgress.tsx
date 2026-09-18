import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ArrowRightIcon, ClockIcon, CloseIcon } from "@/components/ui/icons";
import { WorkflowBlockers } from "@/components/projects/WorkflowBlockers";
import { WORKFLOW_ROLE_LABELS, WORKFLOW_ROLE_TONE } from "@/types/workflow";
import type { ProjectWorkflowDetail, WorkflowTransitionOption } from "@/types/workflow";

/**
 * GeoCore Premium OS Plan 01 (Sprint 040, Task 8) — the Workflow tab's
 * main panel. Shows the project's current stage (role + trade-specific
 * label, never one without the other) and every stage it could legally
 * move to next, each rendered exactly as GET /projects/{id}/workflow
 * describes it. Deliberately does not attempt to draw a full linear
 * progress bar across every stage in the template — no endpoint exposes
 * a template's complete ordered stage list, and fabricating one from the
 * handful of stages this project happens to have touched would be
 * exactly the kind of invented state Plan 01 forbids.
 */
export function WorkflowProgress({
  detail,
  canManage,
  pendingKey,
  onTransition,
}: {
  detail: ProjectWorkflowDetail;
  canManage: boolean;
  pendingKey: string | null;
  onTransition: (option: WorkflowTransitionOption) => void;
}) {
  const forward = detail.allowed_transitions.filter(
    (option) => option.stage_key !== "on_hold" && option.stage_key !== "cancelled"
  );
  const hold = detail.allowed_transitions.find((option) => option.stage_key === "on_hold");
  const cancel = detail.allowed_transitions.find((option) => option.stage_key === "cancelled");

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="text-xs font-medium text-muted">Current stage</p>
          <div className="mt-1 flex items-center gap-2">
            <Badge tone={WORKFLOW_ROLE_TONE[detail.role]}>
              {WORKFLOW_ROLE_LABELS[detail.role]}
            </Badge>
            <span className="text-sm font-medium text-foreground">{detail.stage_label}</span>
          </div>
        </div>
        <span className="text-xs text-muted">on {detail.template_name}</span>
      </div>

      {detail.is_terminal && (
        <p className="mt-4 text-sm text-muted">
          This project&apos;s workflow has reached a terminal stage — no further move is possible.
        </p>
      )}

      {!detail.is_terminal && canManage && forward.length > 0 && (
        <div className="mt-5">
          <p className="text-xs font-medium text-muted">Next steps</p>
          <div className="mt-2 flex flex-col gap-2">
            {forward.map((option) => {
              const blocked = option.blocked_requirements.length > 0;
              return (
                <div key={option.stage_key}>
                  <Button
                    variant="outline"
                    onClick={() => onTransition(option)}
                    disabled={blocked || pendingKey !== null}
                  >
                    <ArrowRightIcon className="h-4 w-4" />
                    {pendingKey === option.stage_key ? "Moving…" : `Move to ${option.stage_label}`}
                  </Button>
                  <WorkflowBlockers blockers={option.blocked_requirements} />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!detail.is_terminal && canManage && (hold || cancel) && (
        <div className="mt-5 flex flex-wrap gap-2 border-t border-border pt-4">
          {hold && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onTransition(hold)}
              disabled={hold.blocked_requirements.length > 0 || pendingKey !== null}
            >
              <ClockIcon className="h-4 w-4" />
              {pendingKey === hold.stage_key ? "Holding…" : "Hold"}
            </Button>
          )}
          {cancel && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onTransition(cancel)}
              disabled={cancel.blocked_requirements.length > 0 || pendingKey !== null}
            >
              <CloseIcon className="h-4 w-4" />
              {pendingKey === cancel.stage_key ? "Cancelling…" : "Cancel"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
