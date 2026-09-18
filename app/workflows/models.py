"""Shared workflow types (GeoCore Premium OS Plan 01, Task 2+).

`WorkflowRole` is the stable cross-trade reporting vocabulary — dashboards,
automations and AI read it. `SystemWorkflowStage`/`SystemWorkflowTemplate`
describe GeoCore's built-in, immutable per-trade stage sequences; the
persisted, versioned equivalents live in app/database/models.py and are
seeded from these at migration time (Task 3).
"""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.workflows.gates import GateBlocker


class WorkflowRole(str, Enum):
    """The 13 semantic roles every workflow stage maps to. Two different
    trades' stages ("Fabrication" for stone, "First Fix" for electrical)
    can share a role (IN_PROGRESS) while each project still displays its
    own trade-specific label — this is what makes company-wide reporting
    possible without forcing one industry's vocabulary onto another."""

    LEAD = "lead"
    SURVEY = "survey"
    QUOTED = "quoted"
    APPROVED = "approved"
    PROCUREMENT = "procurement"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    INSPECTION = "inspection"
    SNAGGING = "snagging"
    HANDOVER = "handover"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class SystemWorkflowStage(BaseModel):
    """One stage in a system (GeoCore-provided) workflow template. `key` is
    stable per template and is what persistence/transitions/gates key off
    — never the (freely rewordable) `label`."""

    key: str
    label: str
    role: WorkflowRole
    position: int
    terminal: bool = False


class SystemWorkflowTemplate(BaseModel):
    """An immutable, GeoCore-provided workflow for one trade. `key` follows
    `f"{trade_key}_v1"` (e.g. "electrical_v1"), except the safe fallback
    template, which is "general_v1" and is used for `trade_key="other"`
    and for any unknown/absent trade."""

    key: str
    name: str
    trade_key: str
    stages: tuple[SystemWorkflowStage, ...]


class ProjectWorkflowSummary(BaseModel):
    """The workflow-facing part of a ProjectOut response (Task 4). Nested
    under `ProjectOut.workflow` alongside the legacy `status` field, which
    stays present unchanged during this migration period."""

    template_key: str
    template_name: str
    stage_key: str
    stage_label: str
    role: WorkflowRole


class WorkflowTransitionRequest(BaseModel):
    """Body of POST /projects/{id}/workflow/transition (Task 5). Hold and
    Cancel are requested the same way as any forward move — target_stage_key
    "on_hold"/"cancelled" — Resume is requested by passing the key of the
    stage the project was on before it was held, which the service layer
    recognises via the project's own workflow_previous_active_stage_id
    rather than a static graph edge."""

    target_stage_key: str
    reason: str | None = None


class WorkflowTransitionOption(BaseModel):
    """One stage a project could move to next. `blocked_requirements` is
    always empty as of Task 5 — Task 6 populates it by evaluating that
    target stage's own WorkflowStage.gate_definitions against the project's
    real state, never fabricating a requirement that doesn't exist yet.
    Full GateBlocker objects (code + message), not bare codes — Task 8's
    Project 360 Workflow tab reads `message` directly rather than keeping
    a second, driftable copy of gates.py's own wording."""

    stage_key: str
    stage_label: str
    role: WorkflowRole
    blocked_requirements: list[GateBlocker] = []


class ProjectWorkflowDetail(ProjectWorkflowSummary):
    """GET /projects/{id}/workflow response — the current stage (inherited
    from ProjectWorkflowSummary) plus what can happen next."""

    is_terminal: bool
    allowed_transitions: list[WorkflowTransitionOption]


class WorkflowHistoryEntry(BaseModel):
    """One row of GET /projects/{id}/workflow/history — the append-only
    audit trail backing a future Project 360 Timeline tab."""

    id: uuid.UUID
    from_stage_key: str | None
    from_stage_label: str | None
    to_stage_key: str
    to_stage_label: str
    actor_user_id: uuid.UUID | None
    reason: str | None
    created_at: datetime
