"""Shared workflow types (GeoCore Premium OS Plan 01, Task 2+).

`WorkflowRole` is the stable cross-trade reporting vocabulary — dashboards,
automations and AI read it. `SystemWorkflowStage`/`SystemWorkflowTemplate`
describe GeoCore's built-in, immutable per-trade stage sequences; the
persisted, versioned equivalents live in app/database/models.py and are
seeded from these at migration time (Task 3).
"""

from enum import Enum

from pydantic import BaseModel


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
