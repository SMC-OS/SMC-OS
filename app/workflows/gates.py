"""GeoCore Premium OS Plan 01 (Sprint 040, Task 6) — workflow stage entry
requirements ("gates").

A WorkflowStage's own `gate_definitions` JSONB column (added by Task 3's
migration, unused until now) holds a list of these, validated at the
API/data boundary into a closed set of gate *types* via a Pydantic
discriminated union — never arbitrary code, so a gate can only ever check
one of the specific, hand-written conditions below. Evaluating a target
stage's gates never fabricates project state that doesn't exist: every
check reads a real column or a real related row (Appointment, Quote),
nothing inferred or guessed.

Extensible by design: adding a future gate (payment received, procurement
complete, a required document, a certification, a checklist item) means
adding one more Pydantic variant to `GateDefinition` and one more branch
to `_blocker_for` — app/workflows/service.py's transition engine itself
never needs to change.
"""

import uuid
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import Project, WorkflowStage


class GateBlocker(BaseModel):
    """One unmet requirement blocking a project from entering a stage."""

    code: str
    message: str


class CustomerLinkedGate(BaseModel):
    type: Literal["customer_linked"] = "customer_linked"


class AssignedUserGate(BaseModel):
    type: Literal["assigned_user"] = "assigned_user"


class SiteAddressPresentGate(BaseModel):
    type: Literal["site_address_present"] = "site_address_present"


class CompletedSiteVisitGate(BaseModel):
    type: Literal["completed_site_visit"] = "completed_site_visit"


class ApprovedSourceQuoteGate(BaseModel):
    type: Literal["approved_source_quote"] = "approved_source_quote"


GateDefinition = Annotated[
    Union[
        CustomerLinkedGate,
        AssignedUserGate,
        SiteAddressPresentGate,
        CompletedSiteVisitGate,
        ApprovedSourceQuoteGate,
    ],
    Field(discriminator="type"),
]

_GATE_LIST_ADAPTER: TypeAdapter[list[GateDefinition]] = TypeAdapter(list[GateDefinition])


def parse_gate_definitions(raw: list[dict] | None) -> list[GateDefinition]:
    """Validates a WorkflowStage.gate_definitions JSONB value into the
    closed set of gate types above. An unrecognised `type` (a typo, or a
    future gate seeded by a newer version of this code and read by an
    older one) raises a pydantic ValidationError rather than silently
    admitting an unenforced gate — a broken gate definition must fail
    loudly, never fail open."""
    if not raw:
        return []
    return _GATE_LIST_ADAPTER.validate_python(raw)


def _blocker_for(db: Session, project: Project, tenant_id: uuid.UUID, gate: GateDefinition) -> GateBlocker | None:
    if isinstance(gate, CustomerLinkedGate):
        if project.customer_id is None:
            return GateBlocker(
                code="customer_linked", message="This project has no linked customer yet"
            )
        return None

    if isinstance(gate, AssignedUserGate):
        if project.assigned_user_id is None:
            return GateBlocker(
                code="assigned_user", message="This project has no assigned team member yet"
            )
        return None

    if isinstance(gate, SiteAddressPresentGate):
        if not project.site_address_line1:
            return GateBlocker(
                code="site_address_present", message="This project has no site address yet"
            )
        return None

    if isinstance(gate, CompletedSiteVisitGate):
        appointments = crud.list_appointments_by_project(db, tenant_id, project.id)
        if not any(appointment.status == "completed" for appointment in appointments):
            return GateBlocker(
                code="completed_site_visit",
                message="No completed site visit is recorded for this project yet",
            )
        return None

    if isinstance(gate, ApprovedSourceQuoteGate):
        quote = crud.get_quote_by_id(db, project.quote_id, tenant_id) if project.quote_id else None
        if quote is None or quote.status != "approved":
            return GateBlocker(
                code="approved_source_quote", message="This project has no approved source quote yet"
            )
        return None

    raise AssertionError(f"unreachable gate type: {gate!r}")  # pragma: no cover


def evaluate_stage_gates(
    db: Session, project: Project, tenant_id: uuid.UUID, target_stage: WorkflowStage
) -> list[GateBlocker]:
    """The unmet requirements blocking `project` from entering
    `target_stage` right now. Empty means the move is unobstructed by any
    gate — app/workflows/service.py's transition engine still separately
    checks the move is a legal graph edge (or Resume) before this is ever
    consulted; gates are entry requirements layered on top of that, never
    a replacement for it. The synthetic on_hold/cancelled side stages are
    seeded with no gate_definitions at all (Task 3), so Hold/Cancel/Resume
    are never blocked by a gate without extra handling here."""
    return [
        blocker
        for gate in parse_gate_definitions(target_stage.gate_definitions)
        if (blocker := _blocker_for(db, project, tenant_id, gate)) is not None
    ]
