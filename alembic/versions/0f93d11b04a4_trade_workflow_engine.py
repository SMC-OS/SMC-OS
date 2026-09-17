"""trade workflow engine

Revision ID: 0f93d11b04a4
Revises: b5c6d7e8f9a0
Create Date: 2026-09-17 19:11:53.297885

GeoCore Premium OS, Plan 01 (Adaptive Workflows + Project 360
Foundation) — Task 3. The single schema migration for the whole plan
(per the plan's own global constraint: exactly one new linear revision
from this baseline for the workflow schema).

THE CHANGE: replaces the single hard-coded stone-shaped status pipeline
(app/projects/models.py's ProjectStatus, unchanged and still readable
during this migration period) with a versioned, trade-adaptive workflow
engine: workflow_templates/workflow_stages/workflow_transitions hold an
immutable system template per trade (seeded below from
app.workflows.catalogue.SYSTEM_WORKFLOWS's own data, copied in as plain
literals rather than imported — a migration must stay reproducible even
after that module's Python changes in a later sprint), plus one
"legacy_v1" template that exactly mirrors the seven historical
ProjectStatus values.

LEGACY SAFETY (the critical part): every project that already exists as
of this migration is bound to legacy_v1 at the stage matching its exact
current `status` string — never guessed, never reinterpreted, never
rewritten. `projects.status` itself is untouched by this migration and
keeps working exactly as before for any code that still reads it. New
projects created after this migration bind to the correct system
template for their trade (app/workflows/service.py, Task 4) instead of
legacy_v1.

`projects.workflow_template_id`/`workflow_stage_id` are added nullable,
backfilled, and only then made NOT NULL, so the backfill always
succeeds before the constraint could ever reject a row.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '0f93d11b04a4'
down_revision: Union[str, None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Seed data — a frozen copy of app.workflows.catalogue's template spec at
# the time this migration was written. Deliberately NOT imported from
# app.workflows.catalogue: a migration must keep producing the exact same
# schema/data years from now even after that module's Python is edited or
# deleted in a future sprint.
# ---------------------------------------------------------------------------

# trade_key -> (template name, [(stage label, role), ...])
_SYSTEM_SPEC: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "stone": ("Stone & Worktops", [
        ("Enquiry", "lead"), ("Measure / Site Visit", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Deposit", "procurement"),
        ("Material Ordered / Reserved", "procurement"), ("Template", "in_progress"),
        ("Fabrication", "in_progress"), ("QC", "inspection"), ("Installation", "in_progress"),
        ("Snagging", "snagging"), ("Complete", "completed"),
    ]),
    "general_building": ("General Building", [
        ("Enquiry", "lead"), ("Site Visit", "survey"), ("Estimate / Quote", "quoted"),
        ("Approved", "approved"), ("Deposit", "procurement"), ("Pre-Start", "scheduled"),
        ("In Progress", "in_progress"), ("Inspection", "inspection"), ("Snagging", "snagging"),
        ("Handover", "handover"), ("Complete", "completed"),
    ]),
    "renovation": ("Renovation", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Scope", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Procurement", "procurement"), ("Strip-Out", "in_progress"),
        ("Main Works", "in_progress"), ("Inspection", "inspection"), ("Snagging", "snagging"),
        ("Handover", "handover"), ("Complete", "completed"),
    ]),
    "extension": ("Extensions", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Pre-Construction", "scheduled"), ("Groundworks", "in_progress"),
        ("Structure", "in_progress"), ("First Fix", "in_progress"), ("Second Fix", "in_progress"),
        ("Inspection", "inspection"), ("Snagging", "snagging"), ("Handover", "handover"),
        ("Complete", "completed"),
    ]),
    "electrical": ("Electrical", [
        ("Enquiry", "lead"), ("Site Assessment", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Scheduled", "scheduled"), ("First Fix", "in_progress"),
        ("Second Fix", "in_progress"), ("Testing", "inspection"), ("Certification", "inspection"),
        ("Snagging", "snagging"), ("Complete", "completed"),
    ]),
    "plumbing": ("Plumbing", [
        ("Enquiry", "lead"), ("Site Assessment", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Materials", "procurement"), ("First Fix", "in_progress"),
        ("Second Fix", "in_progress"), ("Pressure / Test Check", "inspection"),
        ("Commissioning", "inspection"), ("Complete", "completed"),
    ]),
    "heating_hvac": ("Heating / HVAC", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Equipment Ordered", "procurement"), ("Installation", "in_progress"),
        ("Testing", "inspection"), ("Commissioning", "inspection"),
        ("Certification", "inspection"), ("Complete", "completed"),
    ]),
    "carpentry": ("Carpentry & Joinery", [
        ("Enquiry", "lead"), ("Measure", "survey"), ("Design / Specification", "survey"),
        ("Quote", "quoted"), ("Approved", "approved"), ("Materials", "procurement"),
        ("Workshop / Fabrication", "in_progress"), ("Installation", "in_progress"),
        ("Finishing", "in_progress"), ("QC", "inspection"), ("Complete", "completed"),
    ]),
    "kitchen": ("Kitchens", [
        ("Enquiry", "lead"), ("Measure", "survey"), ("Design", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Procurement", "procurement"), ("Strip-Out", "in_progress"),
        ("First Fix", "in_progress"), ("Units / Fitting", "in_progress"),
        ("Worktops", "in_progress"), ("Second Fix", "in_progress"), ("Snagging", "snagging"),
        ("Complete", "completed"),
    ]),
    "bathroom": ("Bathrooms", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Procurement", "procurement"), ("Strip-Out", "in_progress"),
        ("Plumbing First Fix", "in_progress"), ("Waterproofing", "in_progress"),
        ("Tiling / Fitting", "in_progress"), ("Second Fix", "in_progress"),
        ("Testing", "inspection"), ("Snagging", "snagging"), ("Complete", "completed"),
    ]),
    "roofing": ("Roofing", [
        ("Enquiry", "lead"), ("Roof Survey", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Materials", "procurement"),
        ("Scaffolding / Access", "scheduled"), ("Strip-Off", "in_progress"),
        ("Installation", "in_progress"), ("Weatherproofing", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "flooring": ("Flooring", [
        ("Enquiry", "lead"), ("Measure", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Material Ordered", "procurement"), ("Subfloor Preparation", "in_progress"),
        ("Installation", "in_progress"), ("Finishing", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "tiling": ("Tiling", [
        ("Enquiry", "lead"), ("Measure", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Materials", "procurement"), ("Preparation / Waterproofing", "in_progress"),
        ("Tiling", "in_progress"), ("Grouting / Finishing", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "decorating": ("Painting & Decorating", [
        ("Enquiry", "lead"), ("Site Visit", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Colour / Specification", "procurement"),
        ("Preparation", "in_progress"), ("Painting / Decoration", "in_progress"),
        ("Touch-Ups", "snagging"), ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "plastering_rendering": ("Plastering & Rendering", [
        ("Enquiry", "lead"), ("Site Visit", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Preparation", "in_progress"), ("Base Coat", "in_progress"),
        ("Finish Coat", "in_progress"), ("Dry / Cure", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "brickwork_masonry": ("Brickwork & Masonry", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Materials", "procurement"), ("Setting Out", "in_progress"),
        ("Construction", "in_progress"), ("Pointing / Finishing", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "groundworks": ("Groundworks", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Permits / Pre-Start", "scheduled"), ("Excavation", "in_progress"),
        ("Drainage / Sub-Base", "in_progress"), ("Concrete / Foundations", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "drainage": ("Drainage", [
        ("Enquiry", "lead"), ("Investigation", "survey"), ("Survey / CCTV", "survey"),
        ("Quote", "quoted"), ("Approved", "approved"), ("Excavation / Access", "in_progress"),
        ("Repair / Installation", "in_progress"), ("Testing", "inspection"),
        ("Reinstatement", "in_progress"), ("Complete", "completed"),
    ]),
    "windows_doors": ("Windows & Doors", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Manufacture / Order", "procurement"), ("Delivery", "procurement"),
        ("Installation", "in_progress"), ("Adjustment", "in_progress"),
        ("Inspection", "inspection"), ("Handover", "handover"), ("Complete", "completed"),
    ]),
    "glazing": ("Glazing", [
        ("Enquiry", "lead"), ("Measure", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Glass Ordered", "procurement"), ("Delivery", "procurement"),
        ("Installation", "in_progress"), ("Sealing", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "landscaping": ("Landscaping", [
        ("Enquiry", "lead"), ("Site Survey", "survey"), ("Design / Scope", "survey"),
        ("Quote", "quoted"), ("Approved", "approved"), ("Procurement", "procurement"),
        ("Ground Preparation", "in_progress"), ("Hard Landscaping", "in_progress"),
        ("Soft Landscaping", "in_progress"), ("Inspection", "inspection"),
        ("Handover", "handover"), ("Complete", "completed"),
    ]),
    "fencing": ("Fencing", [
        ("Enquiry", "lead"), ("Measure", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Materials", "procurement"), ("Ground Preparation", "in_progress"),
        ("Installation", "in_progress"), ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "demolition_stripout": ("Demolition / Strip-Out", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Quote", "quoted"), ("Approved", "approved"),
        ("Safety / Pre-Start", "scheduled"), ("Isolation", "in_progress"),
        ("Strip-Out / Demolition", "in_progress"), ("Waste Removal", "in_progress"),
        ("Site Clearance", "in_progress"), ("Complete", "completed"),
    ]),
    "insulation": ("Insulation", [
        ("Enquiry", "lead"), ("Survey", "survey"), ("Specification", "survey"),
        ("Quote", "quoted"), ("Approved", "approved"), ("Materials", "procurement"),
        ("Preparation", "in_progress"), ("Installation", "in_progress"),
        ("Inspection", "inspection"), ("Certification / Record", "inspection"),
        ("Complete", "completed"),
    ]),
    "steelwork": ("Structural Steelwork", [
        ("Enquiry", "lead"), ("Survey / Drawings", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Engineering / Approval", "scheduled"),
        ("Fabrication", "in_progress"), ("Delivery", "procurement"),
        ("Installation", "in_progress"), ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
    "scaffolding": ("Scaffolding", [
        ("Enquiry", "lead"), ("Site Survey", "survey"), ("Design / Load Requirement", "survey"),
        ("Quote", "quoted"), ("Approved", "approved"), ("Permit / Pre-Start", "scheduled"),
        ("Erection", "in_progress"), ("Inspection / Handover", "handover"),
        ("In Use", "in_progress"), ("Dismantle", "in_progress"), ("Complete", "completed"),
    ]),
    "solar_renewables": ("Solar & Renewables", [
        ("Enquiry", "lead"), ("Site Survey", "survey"), ("Design / Yield Assessment", "survey"),
        ("Quote", "quoted"), ("Approved", "approved"), ("Permissions / Grid", "scheduled"),
        ("Equipment Ordered", "procurement"), ("Installation", "in_progress"),
        ("Electrical Connection", "in_progress"), ("Testing / Commissioning", "inspection"),
        ("Certification", "inspection"), ("Complete", "completed"),
    ]),
    "other": ("General / Custom Trade", [
        ("Enquiry", "lead"), ("Site Visit", "survey"), ("Quote", "quoted"),
        ("Approved", "approved"), ("Scheduled", "scheduled"), ("In Progress", "in_progress"),
        ("Inspection", "inspection"), ("Complete", "completed"),
    ]),
}

# The seven historical ProjectStatus values, unchanged in meaning.
_LEGACY_SPEC: list[tuple[str, str, str]] = [
    # (stage key, label, role) — key equals the exact ProjectStatus value
    # so the backfill below can match a project's `status` string directly.
    ("enquiry", "Enquiry", "lead"),
    ("quoted", "Quoted", "quoted"),
    ("booked", "Booked", "approved"),
    ("templated", "Templated", "in_progress"),
    ("fabricated", "Fabricated", "in_progress"),
    ("installed", "Installed", "in_progress"),
    ("complete", "Complete", "completed"),
]


def _slug(label: str) -> str:
    out = []
    prev_underscore = False
    for ch in label.lower():
        if ch.isalnum():
            out.append(ch)
            prev_underscore = False
        elif not prev_underscore:
            out.append("_")
            prev_underscore = True
    return "".join(out).strip("_")


def upgrade() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("trade_key", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "key", "version", name="uq_workflow_templates_tenant_key_version"),
    )
    op.create_index("ix_workflow_templates_tenant_id", "workflow_templates", ["tenant_id"])

    op.create_table(
        "workflow_stages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_template_id", UUID(as_uuid=True),
            sa.ForeignKey("workflow_templates.id"), nullable=False,
        ),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_side_stage", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gate_definitions", JSONB(), nullable=True),
        sa.UniqueConstraint("workflow_template_id", "key", name="uq_workflow_stages_template_key"),
    )
    op.create_index("ix_workflow_stages_workflow_template_id", "workflow_stages", ["workflow_template_id"])

    op.create_table(
        "workflow_transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workflow_template_id", UUID(as_uuid=True),
            sa.ForeignKey("workflow_templates.id"), nullable=False,
        ),
        sa.Column("from_stage_id", UUID(as_uuid=True), sa.ForeignKey("workflow_stages.id"), nullable=False),
        sa.Column("to_stage_id", UUID(as_uuid=True), sa.ForeignKey("workflow_stages.id"), nullable=False),
        sa.UniqueConstraint(
            "workflow_template_id", "from_stage_id", "to_stage_id", name="uq_workflow_transitions_edge"
        ),
    )
    op.create_index("ix_workflow_transitions_workflow_template_id", "workflow_transitions", ["workflow_template_id"])

    op.create_table(
        "project_workflow_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("from_stage_id", UUID(as_uuid=True), sa.ForeignKey("workflow_stages.id"), nullable=True),
        sa.Column("to_stage_id", UUID(as_uuid=True), sa.ForeignKey("workflow_stages.id"), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_project_workflow_history_tenant_id", "project_workflow_history", ["tenant_id"])
    op.create_index("ix_project_workflow_history_project_id", "project_workflow_history", ["project_id"])

    op.add_column("projects", sa.Column("workflow_template_id", UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column("workflow_stage_id", UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column("workflow_previous_active_stage_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projects_workflow_template_id", "projects", "workflow_templates", ["workflow_template_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_projects_workflow_stage_id", "projects", "workflow_stages", ["workflow_stage_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_projects_workflow_previous_active_stage_id",
        "projects", "workflow_stages", ["workflow_previous_active_stage_id"], ["id"],
    )
    op.create_index("ix_projects_workflow_template_id", "projects", ["workflow_template_id"])
    op.create_index("ix_projects_workflow_stage_id", "projects", ["workflow_stage_id"])

    connection = op.get_bind()

    templates_table = sa.table(
        "workflow_templates",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("tenant_id", UUID(as_uuid=True)),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("trade_key", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("is_system", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )
    stages_table = sa.table(
        "workflow_stages",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("workflow_template_id", UUID(as_uuid=True)),
        sa.column("key", sa.String()),
        sa.column("label", sa.String()),
        sa.column("role", sa.String()),
        sa.column("position", sa.Integer()),
        sa.column("is_terminal", sa.Boolean()),
        sa.column("is_side_stage", sa.Boolean()),
    )
    transitions_table = sa.table(
        "workflow_transitions",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("workflow_template_id", UUID(as_uuid=True)),
        sa.column("from_stage_id", UUID(as_uuid=True)),
        sa.column("to_stage_id", UUID(as_uuid=True)),
    )

    template_rows = []
    stage_rows = []
    transition_rows = []

    # stage_ids_by_template[template_key] = {stage_key: stage_id}, needed
    # both for the ordered-forward/side transition seeding below and for
    # the legacy backfill's per-status lookup afterwards.
    stage_ids_by_template: dict[str, dict[str, uuid.UUID]] = {}

    def _seed_template(trade_key: str | None, template_key: str, name: str, stages_spec: list[tuple[str, str]]):
        template_id = uuid.uuid4()
        template_rows.append({
            "id": template_id, "tenant_id": None, "key": template_key, "name": name,
            "trade_key": trade_key, "version": 1, "is_system": True, "is_active": True,
        })

        ordered_ids: list[uuid.UUID] = []
        stage_ids: dict[str, uuid.UUID] = {}
        last_index = len(stages_spec) - 1
        for position, (label, role) in enumerate(stages_spec):
            stage_id = uuid.uuid4()
            key = _slug(label)
            stage_rows.append({
                "id": stage_id, "workflow_template_id": template_id, "key": key, "label": label,
                "role": role, "position": position, "is_terminal": position == last_index,
                "is_side_stage": False,
            })
            ordered_ids.append(stage_id)
            stage_ids[key] = stage_id

        # Synthetic universal side stages — always last two positions,
        # never part of the ordered forward sequence.
        on_hold_id = uuid.uuid4()
        stage_rows.append({
            "id": on_hold_id, "workflow_template_id": template_id, "key": "on_hold",
            "label": "On Hold", "role": "on_hold", "position": len(stages_spec),
            "is_terminal": False, "is_side_stage": True,
        })
        stage_ids["on_hold"] = on_hold_id

        cancelled_id = uuid.uuid4()
        stage_rows.append({
            "id": cancelled_id, "workflow_template_id": template_id, "key": "cancelled",
            "label": "Cancelled", "role": "cancelled", "position": len(stages_spec) + 1,
            "is_terminal": True, "is_side_stage": True,
        })
        stage_ids["cancelled"] = cancelled_id

        # Linear forward sequence.
        for i in range(len(ordered_ids) - 1):
            transition_rows.append({
                "id": uuid.uuid4(), "workflow_template_id": template_id,
                "from_stage_id": ordered_ids[i], "to_stage_id": ordered_ids[i + 1],
            })
        # Universal side edges: every non-terminal real stage -> On Hold
        # and -> Cancelled; On Hold -> Cancelled. Resume is handled in
        # app/workflows/service.py, not as a graph edge (see module docstring).
        for i, stage_id in enumerate(ordered_ids):
            if i == last_index:
                continue
            transition_rows.append({
                "id": uuid.uuid4(), "workflow_template_id": template_id,
                "from_stage_id": stage_id, "to_stage_id": on_hold_id,
            })
            transition_rows.append({
                "id": uuid.uuid4(), "workflow_template_id": template_id,
                "from_stage_id": stage_id, "to_stage_id": cancelled_id,
            })
        transition_rows.append({
            "id": uuid.uuid4(), "workflow_template_id": template_id,
            "from_stage_id": on_hold_id, "to_stage_id": cancelled_id,
        })

        stage_ids_by_template[template_key] = stage_ids

    for trade_key, (name, stages_spec) in _SYSTEM_SPEC.items():
        template_key = "general_v1" if trade_key == "other" else f"{trade_key}_v1"
        _seed_template(trade_key, template_key, name, stages_spec)

    # Legacy V1 — trade-agnostic, no on_hold/cancelled synthetic stages are
    # needed beyond what _seed_template already adds uniformly; historical
    # projects keep the exact same Hold/Cancel affordance as any other
    # project rather than being second-class citizens of the new engine.
    legacy_template_id = uuid.uuid4()
    template_rows.append({
        "id": legacy_template_id, "tenant_id": None, "key": "legacy_v1",
        "name": "Legacy V1", "trade_key": None, "version": 1, "is_system": True, "is_active": True,
    })
    legacy_stage_ids: dict[str, uuid.UUID] = {}
    last_index = len(_LEGACY_SPEC) - 1
    for position, (key, label, role) in enumerate(_LEGACY_SPEC):
        stage_id = uuid.uuid4()
        stage_rows.append({
            "id": stage_id, "workflow_template_id": legacy_template_id, "key": key, "label": label,
            "role": role, "position": position, "is_terminal": position == last_index,
            "is_side_stage": False,
        })
        legacy_stage_ids[key] = stage_id
    on_hold_id = uuid.uuid4()
    stage_rows.append({
        "id": on_hold_id, "workflow_template_id": legacy_template_id, "key": "on_hold",
        "label": "On Hold", "role": "on_hold", "position": len(_LEGACY_SPEC),
        "is_terminal": False, "is_side_stage": True,
    })
    cancelled_id = uuid.uuid4()
    stage_rows.append({
        "id": cancelled_id, "workflow_template_id": legacy_template_id, "key": "cancelled",
        "label": "Cancelled", "role": "cancelled", "position": len(_LEGACY_SPEC) + 1,
        "is_terminal": True, "is_side_stage": True,
    })
    legacy_ordered_ids = [legacy_stage_ids[key] for key, _, _ in _LEGACY_SPEC]
    for i in range(len(legacy_ordered_ids) - 1):
        transition_rows.append({
            "id": uuid.uuid4(), "workflow_template_id": legacy_template_id,
            "from_stage_id": legacy_ordered_ids[i], "to_stage_id": legacy_ordered_ids[i + 1],
        })
    for i, stage_id in enumerate(legacy_ordered_ids):
        if i == last_index:
            continue
        transition_rows.append({
            "id": uuid.uuid4(), "workflow_template_id": legacy_template_id,
            "from_stage_id": stage_id, "to_stage_id": on_hold_id,
        })
        transition_rows.append({
            "id": uuid.uuid4(), "workflow_template_id": legacy_template_id,
            "from_stage_id": stage_id, "to_stage_id": cancelled_id,
        })
    transition_rows.append({
        "id": uuid.uuid4(), "workflow_template_id": legacy_template_id,
        "from_stage_id": on_hold_id, "to_stage_id": cancelled_id,
    })

    op.bulk_insert(templates_table, template_rows)
    op.bulk_insert(stages_table, stage_rows)
    op.bulk_insert(transitions_table, transition_rows)

    # Legacy backfill: every project that already exists binds to
    # legacy_v1 at the stage matching its own current `status` string —
    # never guessed, never rewritten. `projects.status` itself is
    # untouched.
    for status_key, stage_id in legacy_stage_ids.items():
        if status_key in ("on_hold", "cancelled"):
            continue
        connection.execute(
            sa.text(
                "UPDATE projects SET workflow_template_id = :template_id, "
                "workflow_stage_id = :stage_id WHERE status = :status_key "
                "AND workflow_template_id IS NULL"
            ),
            {"template_id": str(legacy_template_id), "stage_id": str(stage_id), "status_key": status_key},
        )
    # Any project whose status somehow doesn't match one of the seven
    # known values (should not exist, but never leave a row unbound)
    # falls back to the legacy "enquiry" stage — the same safe default
    # app.trades.catalogue.default_quote_kind uses elsewhere in this
    # codebase for "the general case is the default".
    connection.execute(
        sa.text(
            "UPDATE projects SET workflow_template_id = :template_id, workflow_stage_id = :stage_id "
            "WHERE workflow_template_id IS NULL"
        ),
        {"template_id": str(legacy_template_id), "stage_id": str(legacy_stage_ids["enquiry"])},
    )

    op.alter_column("projects", "workflow_template_id", nullable=False)
    op.alter_column("projects", "workflow_stage_id", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_projects_workflow_stage_id", table_name="projects")
    op.drop_index("ix_projects_workflow_template_id", table_name="projects")
    op.drop_constraint("fk_projects_workflow_previous_active_stage_id", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_workflow_stage_id", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_workflow_template_id", "projects", type_="foreignkey")
    op.drop_column("projects", "workflow_previous_active_stage_id")
    op.drop_column("projects", "workflow_stage_id")
    op.drop_column("projects", "workflow_template_id")

    op.drop_table("project_workflow_history")
    op.drop_table("workflow_transitions")
    op.drop_table("workflow_stages")
    op.drop_table("workflow_templates")
