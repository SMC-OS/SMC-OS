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
from sqlalchemy import delete, select

from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Project,
    ProjectMaterialRequirement,
    ProjectWorkflowHistory,
    Tenant,
    WorkflowTemplate,
)


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
    ever put a legacy-bound project on a mismatched stage.

    Hermetic by construction: this test creates one project per historical
    ProjectStatus itself (the migration's backfill only ever touched
    `projects` rows that existed at migration time, so a freshly created,
    empty CI database has none of its own — this must never depend on
    another test, another run, or a developer's local database having left
    any legacy-bound rows behind). It also confirms the thing the backfill
    promises: binding a project to its matching legacy_v1 stage never
    rewrites `projects.status` itself.
    """
    from sqlalchemy import select as sa_select

    from app.database.models import WorkflowStage

    historical_statuses = [
        "enquiry", "quoted", "booked", "templated", "fabricated", "installed", "complete",
    ]

    tenant = _make_tenant(db, "LegacyInvariantTenant")
    legacy_template = crud.get_system_workflow_template_by_key(db, "legacy_v1")
    assert legacy_template is not None

    project_ids = []
    try:
        for status in historical_statuses:
            stage = crud.get_workflow_stage_by_key(db, legacy_template.id, status)
            assert stage is not None, status
            project = Project(
                id=uuid.uuid4(), tenant_id=tenant.id, name=f"Legacy fixture {status}",
                status=status, workflow_template_id=legacy_template.id, workflow_stage_id=stage.id,
            )
            db.add(project)
            db.commit()
            project_ids.append(project.id)

        rows = db.execute(
            sa_select(Project.status, WorkflowStage.key)
            .join(WorkflowTemplate, WorkflowTemplate.id == Project.workflow_template_id)
            .join(WorkflowStage, WorkflowStage.id == Project.workflow_stage_id)
            .where(Project.id.in_(project_ids))
        ).all()
        assert len(rows) == len(historical_statuses)
        for status, stage_key in rows:
            assert stage_key == status

        # The backfill contract binds a project to its matching stage —
        # it must never itself rewrite the legacy `status` column.
        reloaded_statuses = {
            row[0] for row in db.execute(sa_select(Project.status).where(Project.id.in_(project_ids))).all()
        }
        assert reloaded_statuses == set(historical_statuses)
    finally:
        db.execute(delete(Project).where(Project.id.in_(project_ids)))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()


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


# ---------------------------------------------------------------------------
# Task 4 — new project + quote handoff workflow binding
# ---------------------------------------------------------------------------

from app.projects.models import ProjectCreate
from app.projects.service import project_service


def test_a_new_stone_project_binds_to_the_stone_workflow_at_enquiry(db):
    tenant = _make_tenant(db, "Task4StoneTenant")
    project = project_service.create(
        db, ProjectCreate(name="Kitchen worktop", project_type="stone"), tenant_id=tenant.id
    )
    assert project.workflow_template_id is not None
    assert project.workflow_stage_id is not None

    stage = crud.get_workflow_stage(db, project.workflow_stage_id)
    template = crud.get_workflow_template(db, project.workflow_template_id)
    assert template.key == "stone_v1"
    assert stage.key == "enquiry"

    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


def test_a_new_electrical_project_binds_to_the_electrical_workflow(db):
    tenant = _make_tenant(db, "Task4ElectricalTenant")
    project = project_service.create(
        db, ProjectCreate(name="Rewire", project_type="electrical"), tenant_id=tenant.id
    )
    template = crud.get_workflow_template(db, project.workflow_template_id)
    assert template.key == "electrical_v1"

    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


def test_an_unknown_or_absent_trade_project_binds_to_the_general_workflow_not_stone(db):
    tenant = _make_tenant(db, "Task4NoTradeTenant")
    project = project_service.create(db, ProjectCreate(name="Misc job"), tenant_id=tenant.id)
    template = crud.get_workflow_template(db, project.workflow_template_id)
    assert template.key == "general_v1"
    assert template.key != "stone_v1"

    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


def test_project_out_exposes_a_workflow_summary_and_keeps_legacy_status():
    from app.projects.models import ProjectOut

    tenant_db = SessionLocal()
    tenant = _make_tenant(tenant_db, "Task4SerializeTenant")
    project = project_service.create(
        tenant_db, ProjectCreate(name="Bathroom refit", project_type="bathroom"), tenant_id=tenant.id
    )

    out = ProjectOut.model_validate(project)
    assert out.status == "enquiry"  # legacy field still present/correct
    assert out.workflow.template_key == "bathroom_v1"
    assert out.workflow.stage_key == "enquiry"
    assert out.workflow.role == WorkflowRole.LEAD

    tenant_db.execute(delete(Project).where(Project.id == project.id))
    tenant_db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
    tenant_db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    tenant_db.commit()
    tenant_db.close()


def test_quote_handoff_binds_the_projects_workflow_from_the_quotes_trade(client, auth_headers):
    """Real HTTP: create a stone quote, approve it, hand it off, and
    prove the resulting Project is bound to the stone workflow — the
    same trade the quote itself was for, not a guess and not general."""
    from app.database.models import Customer, QuoteItem, Quote as QuoteModel

    customer = client.post(
        "/api/v1/customers", json={"name": "Task4 Handoff Customer"}, headers=auth_headers
    )
    assert customer.status_code == 201
    quote = client.post(
        "/api/v1/quote",
        json={
            "customer": "Task4 Handoff Customer",
            "customer_id": customer.json()["id"],
            "material": "Calacatta Gold",
            "thickness": "20mm",
            "kitchen_length": 3.0,
            "postcode": "TASK4-HANDOFF",
        },
        headers=auth_headers,
    )
    assert quote.status_code == 200
    quote_id = quote.json()["id"]

    approved = client.post(f"/api/v1/quotes/{quote_id}/approve", headers=auth_headers)
    assert approved.status_code == 200

    handed_off = client.post(f"/api/v1/quotes/{quote_id}/handoff", headers=auth_headers)
    assert handed_off.status_code == 200
    project_body = handed_off.json()
    assert project_body["workflow"]["template_key"] == "stone_v1"
    assert project_body["workflow"]["stage_key"] == "enquiry"

    session = SessionLocal()
    session.execute(delete(Project).where(Project.id == uuid.UUID(project_body["id"])))
    session.execute(delete(QuoteItem).where(QuoteItem.quote_id == uuid.UUID(quote_id)))
    session.execute(delete(QuoteModel).where(QuoteModel.id == uuid.UUID(quote_id)))
    session.execute(delete(ActivityLog).where(ActivityLog.description.like(f"%{quote_id}%")))
    session.execute(delete(Customer).where(Customer.id == uuid.UUID(customer.json()["id"])))
    session.commit()
    session.close()


# ---------------------------------------------------------------------------
# Task 5 — transition engine, Hold/Resume/Cancel and workflow history
#
# electrical_v1's ordered sequence (see app/workflows/catalogue.py) is
# enquiry -> site_assessment -> quote -> approved -> scheduled ->
# first_fix -> second_fix -> testing -> certification -> snagging ->
# complete; general_v1's is enquiry -> site_visit -> quote -> approved ->
# scheduled -> in_progress -> inspection -> complete. Only adjacent
# positions have a real graph edge — anything else (a skip, a repeat, a
# backward move) must be rejected.
# ---------------------------------------------------------------------------

from app.projects.models import ProjectStatus
from app.workflows.service import get_project_workflow

TASK5_PREFIX = "Pytest Task5 WF"


def _cleanup_task5_project(name: str) -> None:
    session = SessionLocal()
    try:
        ids = [row[0] for row in session.execute(select(Project.id).where(Project.name == name)).all()]
        if ids:
            session.execute(delete(ProjectWorkflowHistory).where(ProjectWorkflowHistory.project_id.in_(ids)))
            session.execute(delete(Project).where(Project.id.in_(ids)))
        session.execute(delete(ActivityLog).where(ActivityLog.description == name))
        session.commit()
    finally:
        session.close()


def _create_project(client, headers, name: str, project_type: str | None) -> str:
    payload = {"name": name}
    if project_type is not None:
        payload["project_type"] = project_type
    resp = client.post("/api/v1/projects", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_get_workflow_returns_current_stage_and_allowed_forward_hold_cancel(client, auth_headers):
    name = f"{TASK5_PREFIX} GetDetail"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        resp = client.get(f"/api/v1/projects/{project_id}/workflow", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["template_key"] == "electrical_v1"
        assert body["stage_key"] == "enquiry"
        assert body["role"] == "lead"
        assert body["is_terminal"] is False

        option_keys = {o["stage_key"] for o in body["allowed_transitions"]}
        assert option_keys == {"site_assessment", "on_hold", "cancelled"}
        for option in body["allowed_transitions"]:
            assert option["blocked_requirements"] == []
    finally:
        _cleanup_task5_project(name)


def test_forward_transition_moves_the_project_and_is_recorded_in_history(client, auth_headers):
    name = f"{TASK5_PREFIX} Forward"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        resp = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "site_assessment", "reason": "Booked a survey"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workflow"]["stage_key"] == "site_assessment"
        assert body["workflow"]["role"] == "survey"
        # The legacy status field is untouched by a workflow-engine move on
        # a project that was never bound to legacy_v1 in the first place.
        assert body["status"] == "enquiry"

        history = client.get(f"/api/v1/projects/{project_id}/workflow/history", headers=auth_headers)
        assert history.status_code == 200
        rows = history.json()
        assert len(rows) == 1
        assert rows[0]["from_stage_key"] == "enquiry"
        assert rows[0]["to_stage_key"] == "site_assessment"
        assert rows[0]["reason"] == "Booked a survey"
        assert rows[0]["actor_user_id"] is not None
    finally:
        _cleanup_task5_project(name)


def test_skipping_a_stage_is_rejected_with_409(client, auth_headers):
    name = f"{TASK5_PREFIX} Skip"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        resp = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "quote"},
            headers=auth_headers,
        )
        assert resp.status_code == 409
    finally:
        _cleanup_task5_project(name)


def test_unknown_target_stage_key_returns_404(client, auth_headers):
    name = f"{TASK5_PREFIX} Unknown"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        resp = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "not-a-real-stage"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
    finally:
        _cleanup_task5_project(name)


def test_hold_then_resume_round_trip(client, auth_headers):
    name = f"{TASK5_PREFIX} HoldResume"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        moved = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=auth_headers,
        )
        assert moved.status_code == 200

        held = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "on_hold", "reason": "Customer paused the job"},
            headers=auth_headers,
        )
        assert held.status_code == 200
        assert held.json()["workflow"]["stage_key"] == "on_hold"
        assert held.json()["workflow"]["role"] == "on_hold"

        detail = client.get(f"/api/v1/projects/{project_id}/workflow", headers=auth_headers).json()
        assert detail["is_terminal"] is False
        option_keys = [o["stage_key"] for o in detail["allowed_transitions"]]
        assert option_keys[0] == "site_assessment"  # Resume target, listed first
        assert "cancelled" in option_keys

        resumed = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=auth_headers,
        )
        assert resumed.status_code == 200
        assert resumed.json()["workflow"]["stage_key"] == "site_assessment"

        history = client.get(f"/api/v1/projects/{project_id}/workflow/history", headers=auth_headers).json()
        assert [row["to_stage_key"] for row in history] == ["site_assessment", "on_hold", "site_assessment"]
    finally:
        _cleanup_task5_project(name)


def test_cancel_is_terminal_and_blocks_further_transitions(client, auth_headers):
    name = f"{TASK5_PREFIX} Cancel"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        cancelled = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "cancelled", "reason": "Customer withdrew"},
            headers=auth_headers,
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["workflow"]["role"] == "cancelled"

        detail = client.get(f"/api/v1/projects/{project_id}/workflow", headers=auth_headers).json()
        assert detail["is_terminal"] is True
        assert detail["allowed_transitions"] == []

        blocked = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "enquiry"},
            headers=auth_headers,
        )
        assert blocked.status_code == 409
    finally:
        _cleanup_task5_project(name)


def test_completing_the_full_sequence_reaches_a_terminal_stage(client, auth_headers):
    name = f"{TASK5_PREFIX} FullRun"
    try:
        project_id = _create_project(client, auth_headers, name, None)  # -> general_v1

        forward_keys = [
            "site_visit", "quote", "approved", "scheduled", "in_progress", "inspection", "complete",
        ]
        for key in forward_keys:
            resp = client.post(
                f"/api/v1/projects/{project_id}/workflow/transition",
                json={"target_stage_key": key},
                headers=auth_headers,
            )
            assert resp.status_code == 200, (key, resp.text)

        detail = client.get(f"/api/v1/projects/{project_id}/workflow", headers=auth_headers).json()
        assert detail["stage_key"] == "complete"
        assert detail["is_terminal"] is True
        assert detail["allowed_transitions"] == []

        blocked = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "on_hold"},
            headers=auth_headers,
        )
        assert blocked.status_code == 409
    finally:
        _cleanup_task5_project(name)


def test_cross_tenant_project_workflow_endpoints_all_404(client, auth_headers, other_tenant_auth_headers):
    name = f"{TASK5_PREFIX} CrossTenant"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        get_resp = client.get(f"/api/v1/projects/{project_id}/workflow", headers=other_tenant_auth_headers)
        assert get_resp.status_code == 404

        history_resp = client.get(
            f"/api/v1/projects/{project_id}/workflow/history", headers=other_tenant_auth_headers
        )
        assert history_resp.status_code == 404

        transition_resp = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "on_hold"},
            headers=other_tenant_auth_headers,
        )
        assert transition_resp.status_code == 404
    finally:
        _cleanup_task5_project(name)


def test_legacy_bound_project_status_endpoint_keeps_workflow_in_sync(db):
    """A pre-existing (legacy_v1-bound) project moved through the old
    PATCH /status endpoint must have its `workflow` view move in lockstep
    — the one binding where a 1:1 stage-key mapping actually exists. A
    project on a real trade workflow is deliberately NOT exercised here:
    ProjectService.update_status leaves `workflow` alone for those, proven
    separately by test_forward_transition_... above (status stays
    "enquiry" after a pure workflow-engine move)."""
    tenant = _make_tenant(db, "Task5LegacySyncTenant")
    legacy_template = crud.get_system_workflow_template_by_key(db, "legacy_v1")
    enquiry_stage = crud.get_workflow_stage_by_key(db, legacy_template.id, "enquiry")

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="Legacy sync job", status="enquiry",
        workflow_template_id=legacy_template.id, workflow_stage_id=enquiry_stage.id,
    )
    db.add(project)
    db.commit()

    updated = project_service.update_status(db, project.id, tenant.id, ProjectStatus.QUOTED)
    assert updated.status == "quoted"

    summary = get_project_workflow(db, updated, tenant.id)
    assert summary.template_key == "legacy_v1"
    assert summary.stage_key == "quoted"

    history = crud.list_project_workflow_history(db, project.id, tenant.id)
    assert len(history) == 1
    quoted_stage = crud.get_workflow_stage_by_key(db, legacy_template.id, "quoted")
    assert history[0].from_stage_id == enquiry_stage.id
    assert history[0].to_stage_id == quoted_stage.id

    db.execute(delete(ProjectWorkflowHistory).where(ProjectWorkflowHistory.project_id == project.id))
    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


def test_legacy_bound_project_workflow_transition_keeps_status_in_sync(db):
    """The mirror of the test above: driving a legacy_v1-bound project
    through the NEW POST /workflow/transition endpoint must also keep the
    legacy `status` field correct - not just the other way round - so
    Project 360 (Task 8) can use the one endpoint for every project's
    advancement action, legacy-bound or not, without leaving `status`
    stale for every other consumer (PipelineCounts, the pre-Task-8
    frontend) that still reads it."""
    from app.workflows.service import transition_project_workflow

    tenant = _make_tenant(db, "Task5LegacyReverseSyncTenant")
    legacy_template = crud.get_system_workflow_template_by_key(db, "legacy_v1")
    enquiry_stage = crud.get_workflow_stage_by_key(db, legacy_template.id, "enquiry")

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="Legacy reverse sync job", status="enquiry",
        workflow_template_id=legacy_template.id, workflow_stage_id=enquiry_stage.id,
    )
    db.add(project)
    db.commit()

    updated = transition_project_workflow(db, project, tenant.id, "quoted", None, None)
    assert updated.status == "quoted"
    assert updated.workflow_stage_id == crud.get_workflow_stage_by_key(db, legacy_template.id, "quoted").id

    # Hold has no legacy status equivalent - `status` must stay untouched.
    held = transition_project_workflow(db, updated, tenant.id, "on_hold", None, None)
    assert held.status == "quoted"
    assert get_project_workflow(db, held, tenant.id).role == WorkflowRole.ON_HOLD

    db.execute(delete(ProjectWorkflowHistory).where(ProjectWorkflowHistory.project_id == project.id))
    db.execute(delete(Project).where(Project.id == project.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


# ---------------------------------------------------------------------------
# Task 6 — workflow stage entry gates
#
# No system template seeded any gate_definitions until GeoCore Premium OS
# Plan 05 (Sprint 044, Task 27) added exactly one real one — stone_v1's
# `fabrication` stage now carries `materials_ready` (see migration
# 3c4d5e6f7a8b). Most of the tests below still set a stage's
# gate_definitions directly via the ORM, exactly the way a future admin
# endpoint eventually would, and always restore it afterwards so no other
# test in this shared database sees an unexpected gate on a template it
# also uses.
# ---------------------------------------------------------------------------

from app.workflows.gates import (
    ApprovedSourceQuoteGate,
    AssignedUserGate,
    CompletedSiteVisitGate,
    CustomerLinkedGate,
    GateBlocker,
    MaterialsReadyGate,
    SiteAddressPresentGate,
    evaluate_stage_gates,
    parse_gate_definitions,
)


def test_parse_gate_definitions_validates_the_closed_set_of_types():
    parsed = parse_gate_definitions(
        [
            {"type": "customer_linked"},
            {"type": "assigned_user"},
            {"type": "site_address_present"},
            {"type": "completed_site_visit"},
            {"type": "approved_source_quote"},
        ]
    )
    assert [type(gate) for gate in parsed] == [
        CustomerLinkedGate, AssignedUserGate, SiteAddressPresentGate,
        CompletedSiteVisitGate, ApprovedSourceQuoteGate,
    ]
    assert parse_gate_definitions(None) == []
    assert parse_gate_definitions([]) == []


def test_parse_gate_definitions_rejects_an_unknown_gate_type():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        parse_gate_definitions([{"type": "not_a_real_gate"}])


def test_evaluate_stage_gates_reports_every_unmet_requirement_at_once(db):
    tenant = _make_tenant(db, "Task6GatesTenant")
    template = crud.get_system_workflow_template_by_key(db, "general_v1")
    enquiry = crud.get_workflow_stage_by_key(db, template.id, "enquiry")
    target = crud.get_workflow_stage_by_key(db, template.id, "quote")

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="Gated job", status="enquiry",
        workflow_template_id=template.id, workflow_stage_id=enquiry.id,
    )
    db.add(project)
    db.commit()

    target.gate_definitions = [
        {"type": "customer_linked"},
        {"type": "assigned_user"},
        {"type": "site_address_present"},
        {"type": "completed_site_visit"},
        {"type": "approved_source_quote"},
    ]
    db.add(target)
    db.commit()

    try:
        blockers = evaluate_stage_gates(db, project, tenant.id, target)
        assert {b.code for b in blockers} == {
            "customer_linked", "assigned_user", "site_address_present",
            "completed_site_visit", "approved_source_quote",
        }
        assert all(isinstance(b, GateBlocker) and b.message for b in blockers)
    finally:
        target.gate_definitions = None
        db.add(target)
        db.commit()
        db.execute(delete(Project).where(Project.id == project.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()


def test_evaluate_stage_gates_clears_once_every_requirement_is_met(db):
    from app.auth.service import auth_service
    from app.database.models import Appointment, Customer, Quote, Subscription, User

    tenant = _make_tenant(db, "Task6GatesMetTenant")
    template = crud.get_system_workflow_template_by_key(db, "general_v1")
    enquiry = crud.get_workflow_stage_by_key(db, template.id, "enquiry")
    target = crud.get_workflow_stage_by_key(db, template.id, "quote")

    customer = crud.create_customer(
        db, id=uuid.uuid4(), tenant_id=tenant.id, name="Gate Test Customer", email=None, phone=None
    )
    owner = auth_service.create_user(
        db, tenant_id=tenant.id, name="Gate Test Owner",
        email=f"gate-test-owner-{uuid.uuid4().hex[:8]}@example.invalid",
        password="Gate-Test-Owner-Password-1!", role="Owner",
    )

    quote = Quote(
        id=uuid.uuid4(), tenant_id=tenant.id, customer_id=customer.id,
        quote_kind="stone", trade="stone", status="approved",
    )
    db.add(quote)
    db.commit()

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="Gate Test job", status="enquiry",
        customer_id=customer.id, assigned_user_id=owner.id, site_address_line1="1 Test Street",
        quote_id=quote.id, workflow_template_id=template.id, workflow_stage_id=enquiry.id,
    )
    db.add(project)
    db.commit()

    appointment = Appointment(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, created_by_user_id=owner.id,
        scheduled_at=project.created_at, status="completed",
    )
    db.add(appointment)
    db.commit()

    target.gate_definitions = [
        {"type": "customer_linked"},
        {"type": "assigned_user"},
        {"type": "site_address_present"},
        {"type": "completed_site_visit"},
        {"type": "approved_source_quote"},
    ]
    db.add(target)
    db.commit()

    try:
        blockers = evaluate_stage_gates(db, project, tenant.id, target)
        assert blockers == []
    finally:
        target.gate_definitions = None
        db.add(target)
        db.commit()
        db.execute(delete(Appointment).where(Appointment.project_id == project.id))
        db.execute(delete(Project).where(Project.id == project.id))
        db.execute(delete(Quote).where(Quote.id == quote.id))
        db.execute(delete(Customer).where(Customer.id == customer.id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant.id))
        db.execute(delete(User).where(User.id == owner.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()


def test_transition_endpoint_returns_structured_409_until_the_gate_clears(client, auth_headers):
    """End-to-end through the real HTTP transition endpoint: a stage
    gated on `assigned_user` blocks with a structured 409 body naming the
    unmet requirement, then succeeds once the project is assigned — never
    a bare/generic 409."""
    name = f"{TASK5_PREFIX} GateEndpoint"
    session = SessionLocal()
    template = crud.get_system_workflow_template_by_key(session, "electrical_v1")
    target = crud.get_workflow_stage_by_key(session, template.id, "site_assessment")
    target_id = target.id
    original_gate_definitions = target.gate_definitions
    target.gate_definitions = [{"type": "assigned_user"}]
    session.add(target)
    session.commit()
    session.close()

    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        blocked = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=auth_headers,
        )
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["blocked_requirements"] == [
            {"code": "assigned_user", "message": "This project has no assigned team member yet"}
        ]

        me = client.get("/api/v1/auth/me", headers=auth_headers)
        assert me.status_code == 200
        assigned = client.patch(
            f"/api/v1/projects/{project_id}/assign",
            json={"assigned_user_id": me.json()["id"]},
            headers=auth_headers,
        )
        assert assigned.status_code == 200

        allowed = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=auth_headers,
        )
        assert allowed.status_code == 200
        assert allowed.json()["workflow"]["stage_key"] == "site_assessment"
    finally:
        session = SessionLocal()
        stage = crud.get_workflow_stage(session, target_id)
        stage.gate_definitions = original_gate_definitions
        session.add(stage)
        session.commit()
        session.close()
        _cleanup_task5_project(name)


def test_materials_ready_gate_blocks_then_clears_as_requirements_are_received(db):
    """GeoCore Premium OS Plan 05 (Sprint 044), Task 27 — a project with
    an outstanding material requirement is blocked; a project with zero
    requirements is never blocked (nothing to wait for); a project whose
    only requirement has reached `received` clears the gate."""
    from app.database import crud as procurement_crud

    tenant = _make_tenant(db, "MaterialsGateTenant")
    template = crud.get_system_workflow_template_by_key(db, "general_v1")
    enquiry = crud.get_workflow_stage_by_key(db, template.id, "enquiry")
    target = crud.get_workflow_stage_by_key(db, template.id, "quote")

    project = Project(
        id=uuid.uuid4(), tenant_id=tenant.id, name="Materials gate job", status="enquiry",
        workflow_template_id=template.id, workflow_stage_id=enquiry.id,
    )
    db.add(project)
    db.commit()

    target.gate_definitions = [{"type": "materials_ready"}]
    db.add(target)
    db.commit()

    try:
        # No requirements at all — never blocked.
        assert evaluate_stage_gates(db, project, tenant.id, target) == []

        requirement = procurement_crud.create_material_requirement(
            db, tenant_id=tenant.id, project_id=project.id, description="Quartz worktop", status="required",
        )
        blockers = evaluate_stage_gates(db, project, tenant.id, target)
        assert [b.code for b in blockers] == ["materials_ready"]

        procurement_crud.update_material_requirement(db, requirement, {"status": "received"})
        assert evaluate_stage_gates(db, project, tenant.id, target) == []
    finally:
        target.gate_definitions = None
        db.add(target)
        db.commit()
        db.execute(delete(ProjectMaterialRequirement).where(ProjectMaterialRequirement.project_id == project.id))
        db.execute(delete(Project).where(Project.id == project.id))
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()


def test_stone_v1_fabrication_stage_carries_the_real_seeded_materials_gate(db):
    """The one real, seeded gate this plan ships (migration
    3c4d5e6f7a8b) — not a test-only stub."""
    template = crud.get_system_workflow_template_by_key(db, "stone_v1")
    fabrication = crud.get_workflow_stage_by_key(db, template.id, "fabrication")
    parsed = parse_gate_definitions(fabrication.gate_definitions)
    assert [type(gate) for gate in parsed] == [MaterialsReadyGate]


# ---------------------------------------------------------------------------
# Task 7 — platform consumers (automations) use semantic roles
#
# The dashboard's own pipeline_by_role aggregate is exercised through the
# real HTTP command-centre endpoint in tests/test_command_centre.py
# (test_pipeline_by_role_aggregates_across_trades_and_is_tenant_scoped) and
# the AI context's by_role/recent_projects in tests/test_geocore_ai.py
# (test_context_groups_projects_by_semantic_role_with_trade_stage_labels) —
# both alongside their own existing suites rather than duplicated here.
# ---------------------------------------------------------------------------

from app.automations.subjects import project_subject


def test_project_subject_exposes_workflow_role_alongside_legacy_status(client, auth_headers):
    name = f"{TASK5_PREFIX} SubjectFields"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        session = SessionLocal()
        project = session.get(Project, uuid.UUID(project_id))
        subject = project_subject(project)
        session.close()

        assert subject["status"] == "enquiry"  # legacy field, unchanged
        assert subject["workflow_stage_key"] == "enquiry"
        assert subject["workflow_stage_label"] == "Enquiry"
        assert subject["workflow_role"] == "lead"
        assert subject["previous_workflow_role"] is None
    finally:
        _cleanup_task5_project(name)


def test_project_subject_carries_previous_workflow_role_while_on_hold(client, auth_headers):
    name = f"{TASK5_PREFIX} SubjectHold"
    try:
        project_id = _create_project(client, auth_headers, name, "electrical")

        moved = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "site_assessment"},
            headers=auth_headers,
        )
        assert moved.status_code == 200

        held = client.post(
            f"/api/v1/projects/{project_id}/workflow/transition",
            json={"target_stage_key": "on_hold"},
            headers=auth_headers,
        )
        assert held.status_code == 200

        session = SessionLocal()
        project = session.get(Project, uuid.UUID(project_id))
        subject = project_subject(project)
        session.close()

        assert subject["workflow_role"] == "on_hold"
        assert subject["previous_workflow_role"] == "survey"
    finally:
        _cleanup_task5_project(name)
