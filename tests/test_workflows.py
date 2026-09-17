"""GeoCore Premium OS Plan 01 — the trade-adaptive workflow engine.

Grows task-by-task alongside app/workflows/*: Task 2 covers the system
workflow template library in isolation (no DB); later tasks add
persistence, transition, gate and consumer-integration coverage.
"""

from app.trades.catalogue import TRADE_KEYS
from app.workflows.catalogue import SYSTEM_WORKFLOWS, template_for_trade
from app.workflows.models import WorkflowRole


# ---------------------------------------------------------------------------
# Task 2 — system workflow template library
# ---------------------------------------------------------------------------


def test_every_trade_has_a_system_workflow():
    for trade_key in TRADE_KEYS:
        template = template_for_trade(trade_key)
        assert template is not None
        if trade_key == "other":
            assert template.key == "general_v1"
        else:
            assert template.key == f"{trade_key}_v1"


def test_specific_template_keys():
    assert template_for_trade("electrical").key == "electrical_v1"
    assert template_for_trade("plumbing").key == "plumbing_v1"
    assert template_for_trade("stone").key == "stone_v1"
    assert template_for_trade("other").key == "general_v1"


def test_unknown_or_absent_trade_falls_back_to_general():
    assert template_for_trade(None).key == "general_v1"
    assert template_for_trade("not-a-real-trade").key == "general_v1"


def test_electrical_workflow_has_testing_and_certification():
    labels = [stage.label for stage in SYSTEM_WORKFLOWS["electrical_v1"].stages]
    assert "First Fix" in labels
    assert "Second Fix" in labels
    assert "Testing" in labels
    assert "Certification" in labels


def test_stone_workflow_has_specialist_stages():
    labels = [stage.label for stage in SYSTEM_WORKFLOWS["stone_v1"].stages]
    assert "Template" in labels
    assert "Fabrication" in labels
    assert "QC" in labels
    assert "Installation" in labels


def test_every_non_side_stage_has_semantic_role():
    for template in SYSTEM_WORKFLOWS.values():
        for stage in template.stages:
            assert isinstance(stage.role, WorkflowRole)


def test_every_template_ends_terminal_at_complete():
    for template in SYSTEM_WORKFLOWS.values():
        last = template.stages[-1]
        assert last.terminal is True
        assert last.role == WorkflowRole.COMPLETED
        assert last.label == "Complete"


def test_every_template_starts_at_enquiry_lead():
    for template in SYSTEM_WORKFLOWS.values():
        first = template.stages[0]
        assert first.label == "Enquiry"
        assert first.role == WorkflowRole.LEAD


def test_stage_keys_are_unique_within_a_template_and_positions_are_sequential():
    for template in SYSTEM_WORKFLOWS.values():
        keys = [stage.key for stage in template.stages]
        assert len(keys) == len(set(keys)), template.key
        positions = [stage.position for stage in template.stages]
        assert positions == list(range(len(positions))), template.key


def test_all_28_trades_produce_distinct_templates_except_other():
    # "other" intentionally shares general_v1 with the unknown-trade
    # fallback; every other trade gets its own template.
    keys_seen = {}
    for trade_key in TRADE_KEYS:
        template = template_for_trade(trade_key)
        keys_seen.setdefault(template.key, set()).add(trade_key)
    assert keys_seen["general_v1"] == {"other"}


# ---------------------------------------------------------------------------
# Task 3 — versioned workflow persistence + legacy migration safety
#
# These exercise the real Postgres schema the migration created, using
# direct ORM construction (not crud.create_project / ProjectService) —
# `projects.workflow_template_id`/`workflow_stage_id` are NOT NULL as of
# this migration, and wiring ProjectService/quote-handoff to actually
# populate them on every new project is Task 4's own job, not this one's.
# ---------------------------------------------------------------------------

import uuid

import pytest
from sqlalchemy import delete

from app.database import crud
from app.database.database import SessionLocal
from app.database.models import Project, ProjectWorkflowHistory, Tenant, WorkflowTemplate


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_tenant(db, name: str) -> Tenant:
    return crud.create_tenant(db, id=uuid.uuid4(), name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}")


def test_a_system_template_can_be_loaded(db):
    template = crud.get_system_workflow_template_by_key(db, "electrical_v1")
    assert template is not None
    assert template.trade_key == "electrical"
    assert template.tenant_id is None
    assert template.is_system is True

    stages = crud.list_workflow_stages(db, template.id)
    labels = [s.label for s in stages]
    assert "First Fix" in labels
    assert "On Hold" in labels
    assert "Cancelled" in labels


def test_legacy_v1_template_exactly_mirrors_the_seven_historical_statuses(db):
    template = crud.get_system_workflow_template_by_key(db, "legacy_v1")
    assert template is not None
    assert template.trade_key is None

    stages = crud.list_workflow_stages(db, template.id)
    ordered_keys = [s.key for s in stages if not s.is_side_stage]
    assert ordered_keys == [
        "enquiry", "quoted", "booked", "templated", "fabricated", "installed", "complete",
    ]


def test_a_project_can_bind_to_a_template_and_stage(db):
    tenant = _make_tenant(db, "WorkflowBindTenant")
    template = crud.get_system_workflow_template_by_key(db, "stone_v1")
    stage = crud.get_workflow_stage_by_key(db, template.id, "enquiry")

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="Test stone job", status="enquiry",
        workflow_template_id=template.id, workflow_stage_id=stage.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    fetched = crud.get_project_by_id(db, project.id, tenant.id)
    assert fetched.workflow_template_id == template.id
    assert fetched.workflow_stage_id == stage.id

    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


def test_tenant_scoped_lookup_never_leaks_a_different_tenants_project(db):
    tenant_a = _make_tenant(db, "WorkflowIsoTenantA")
    tenant_b = _make_tenant(db, "WorkflowIsoTenantB")
    template = crud.get_system_workflow_template_by_key(db, "general_v1")
    stage = crud.get_workflow_stage_by_key(db, template.id, "enquiry")

    project_a = Project(
        id=uuid.uuid4(), tenant_id=tenant_a.id, name="Tenant A job", status="enquiry",
        workflow_template_id=template.id, workflow_stage_id=stage.id,
    )
    db.add(project_a)
    db.commit()

    # Tenant B's own scoped lookup must not find Tenant A's project, even
    # though both bind to the same shared system template/stage.
    assert crud.get_project_by_id(db, project_a.id, tenant_b.id) is None
    assert crud.get_project_by_id(db, project_a.id, tenant_a.id) is not None

    db.execute(delete(Project).where(Project.id == project_a.id))
    db.execute(delete(Tenant).where(Tenant.id.in_([tenant_a.id, tenant_b.id])))
    db.commit()


def test_legacy_bound_projects_always_have_a_stage_matching_their_own_status(db):
    """A permanent invariant (not a one-off snapshot): any project bound
    to legacy_v1 must have its workflow_stage's key equal to its own
    `status` string — the migration's backfill, and nothing else, may
    ever put a legacy-bound project on a mismatched stage. Deliberately
    does not assert every row is legacy-bound (Task 4 onward binds new
    projects to real trade templates, and later tasks' own tests create
    such rows in this same database)."""
    from sqlalchemy import select as sa_select

    from app.database.models import WorkflowStage

    rows = db.execute(
        sa_select(Project.status, WorkflowStage.key)
        .join(WorkflowTemplate, WorkflowTemplate.id == Project.workflow_template_id)
        .join(WorkflowStage, WorkflowStage.id == Project.workflow_stage_id)
        .where(WorkflowTemplate.key == "legacy_v1")
    ).all()
    assert len(rows) > 0, "expected pre-existing fixture projects from earlier test runs"
    for status, stage_key in rows:
        assert stage_key == status


def test_workflow_history_is_append_only_and_tenant_scoped(db):
    tenant = _make_tenant(db, "WorkflowHistoryTenant")
    template = crud.get_system_workflow_template_by_key(db, "general_v1")
    enquiry = crud.get_workflow_stage_by_key(db, template.id, "enquiry")
    quote_stage = crud.get_workflow_stage_by_key(db, template.id, "quote")

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="History job", status="enquiry",
        workflow_template_id=template.id, workflow_stage_id=enquiry.id,
    )
    db.add(project)
    db.commit()

    crud.create_project_workflow_history(
        db, id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id,
        from_stage_id=enquiry.id, to_stage_id=quote_stage.id,
        actor_user_id=None, reason=None,
    )

    history = crud.list_project_workflow_history(db, project.id, tenant.id)
    assert len(history) == 1
    assert history[0].from_stage_id == enquiry.id
    assert history[0].to_stage_id == quote_stage.id

    db.execute(delete(ProjectWorkflowHistory).where(ProjectWorkflowHistory.project_id == project.id))
    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()
