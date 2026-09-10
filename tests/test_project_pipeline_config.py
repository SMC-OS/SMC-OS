"""Per-tenant pipeline configuration — Sprint 039, Workstream D.

Covers the database-backed half of the pipeline: seeding a tenant's
stages from a named template, resolving them back, tenant isolation, and
the drift guard that keeps Sprint 039's migration honest about the legacy
stone vocabulary it seeds existing tenants with.

The pure vocabulary/graph is covered in tests/test_project_pipeline.py.
"""

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy import delete

from app.database import crud
from app.database.database import SessionLocal
from app.database.models import PipelineStage, Tenant
from app.projects import pipeline, pipeline_config

RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"Pytest Pipeline Config {RUN_ID}"

_VERSIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load_migration(module_name: str):
    """Import a migration module by path.

    `alembic/versions/` is deliberately not a Python package (Alembic loads
    revisions by file path), so a plain `import` cannot reach one.
    """
    spec = importlib.util.spec_from_file_location(
        module_name, _VERSIONS_DIR / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cleanup():
    db = SessionLocal()
    try:
        tenant_ids = [
            row.id
            for row in db.query(Tenant).filter(Tenant.name.like(f"{TEST_PREFIX}%")).all()
        ]
        if tenant_ids:
            db.execute(delete(PipelineStage).where(PipelineStage.tenant_id.in_(tenant_ids)))
            db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture()
def tenant(db):
    """A bare tenant with no pipeline configured — created through crud
    rather than TenantService so seeding is something each test opts into
    explicitly."""
    row = crud.create_tenant(
        db,
        id=uuid.uuid4(),
        name=f"{TEST_PREFIX} {uuid.uuid4().hex[:6]}",
        slug=f"pytest-pipeline-{uuid.uuid4().hex[:10]}",
    )
    return row


def test_a_tenant_with_no_configured_stages_resolves_to_the_standard_pipeline(db, tenant):
    """Defence in depth. A tenant created by some path that forgot to seed
    must still have a working, trade-neutral pipeline rather than a
    project screen that cannot render."""
    resolved = pipeline_config.resolve(db, tenant.id)

    assert [stage.key for stage in resolved.stages] == [
        stage.key for stage in pipeline.template("standard")
    ]


def test_seeding_persists_the_template_and_resolve_reads_it_back(db, tenant):
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="stone")

    resolved = pipeline_config.resolve(db, tenant.id)

    assert [stage.key for stage in resolved.stages] == [
        stage.key for stage in pipeline.template("stone")
    ]
    assert resolved.role_of("fabricated") == "in_progress"


def test_seeding_is_idempotent_and_never_duplicates_a_tenant_s_stages(db, tenant):
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="standard")
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="standard")

    rows = db.query(PipelineStage).filter(PipelineStage.tenant_id == tenant.id).all()

    assert len(rows) == len(pipeline.template("standard"))


def test_re_seeding_never_silently_switches_an_already_configured_tenant(db, tenant):
    """A tenant already on the stone pipeline must not be quietly moved to
    the standard one by a later seed call — switching template is a
    deliberate, previewed action (`apply_template`), never a side effect."""
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="stone")
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="standard")

    resolved = pipeline_config.resolve(db, tenant.id)

    assert resolved.get("fabricated") is not None


def test_stages_resolve_in_this_tenant_s_own_position_order(db, tenant):
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="stone")

    positions = [stage.position for stage in pipeline_config.resolve(db, tenant.id).stages]

    assert positions == sorted(positions)


def test_one_tenant_s_pipeline_never_leaks_into_another_s(db, tenant):
    other = crud.create_tenant(
        db,
        id=uuid.uuid4(),
        name=f"{TEST_PREFIX} other {uuid.uuid4().hex[:6]}",
        slug=f"pytest-pipeline-other-{uuid.uuid4().hex[:10]}",
    )
    pipeline_config.seed_for_tenant(db, tenant.id, template_key="stone")
    pipeline_config.seed_for_tenant(db, other.id, template_key="standard")

    assert pipeline_config.resolve(db, tenant.id).get("fabricated") is not None
    assert pipeline_config.resolve(db, other.id).get("fabricated") is None


def test_a_brand_new_workspace_is_seeded_with_the_trade_neutral_pipeline(
    client, other_tenant_auth_headers, db
):
    """The whole point of Workstream D: a business signing up today never
    meets stone vocabulary. Exercised through the real signup path, not by
    calling the seeder directly."""
    me = client.get("/api/v1/auth/me", headers=other_tenant_auth_headers).json()

    resolved = pipeline_config.resolve(db, uuid.UUID(me["tenant_id"]))

    assert [stage.key for stage in resolved.active_stages] == [
        "lead",
        "quoted",
        "approved",
        "scheduled",
        "in_progress",
        "completed",
    ]


def test_the_migration_s_legacy_rows_match_the_stone_template_exactly():
    """Drift guard. Sprint 039's migration hardcodes the stone stages as
    literal SQL values (a migration must never import application code
    that can change under it). This test is what keeps that copy honest:
    if anyone edits the stone template, this fails until the migration's
    recorded snapshot is reconciled deliberately.
    """
    migration = _load_migration("c5d6e7f8a9b0_add_pipeline_stages")

    assert migration.LEGACY_STONE_STAGES == tuple(
        (stage.key, stage.label, stage.role, stage.position)
        for stage in pipeline.template("stone")
    )
