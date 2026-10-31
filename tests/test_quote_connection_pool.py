"""A quote save must not need a second database connection for its audit event."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.activity import repository
from app.database.models import ActivityLog, Project, Quote, QuoteItem, Tenant, WorkflowStage, WorkflowTemplate
from uuid import uuid4
from app.quotes import service
from app.quotes.models import QuoteRequest
from app.quotes.general import GeneralQuoteRequest


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
def quote_db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'quotes.db'}", pool_size=1, max_overflow=0,
        pool_timeout=0.1,
    )
    for model in (Tenant, Quote, QuoteItem, ActivityLog, Project, WorkflowTemplate, WorkflowStage):
        model.__table__.create(engine)
    monkeypatch.setattr(repository, "SessionLocal", sessionmaker(bind=engine))
    # Automation rules are a separate, already-tested subsystem. Keep the
    # real activity repository and all quote persistence in this regression.
    monkeypatch.setattr(service.automation_dispatcher, "dispatch_quote_created", lambda *a: None)
    monkeypatch.setattr(service.automation_dispatcher, "dispatch_quote_approved", lambda *a: None)
    with Session(engine) as db:
        tenant = Tenant(name="Synthetic pool test", slug="synthetic-pool")
        from app.workflows.catalogue import template_for_trade
        template = WorkflowTemplate(key=template_for_trade("stone").key, name="Synthetic workflow", is_system=True)
        db.add(template)
        db.flush()
        db.add(WorkflowStage(workflow_template_id=template.id, key="booked", label="Booked", role="booked", position=0))
        db.add(tenant)
        db.commit()
        yield db, tenant.id
    engine.dispose()


def _request():
    return QuoteRequest(
        customer="Synthetic pool customer", site_address_line1="1 Test Street",
        postcode="NW2 7RP", pricing_mode="manual", manual_price=1200,
        items=[dict(material="Synthetic quartz", thickness="20mm", length_mm=2000)],
    )


def _create(db, tenant_id, kind):
    if kind == "stone":
        return service.QuoteService().create(db, _request(), tenant_id)
    return service.QuoteService().create_general(db, GeneralQuoteRequest(
        title="Synthetic general quote", lines=[dict(line_kind="labour", description="Synthetic labour", quantity=1, unit="job", unit_price=1200)],
    ), tenant_id)


@pytest.mark.parametrize("kind", ["stone", "general"])
def test_quote_and_activity_save_using_one_connection(quote_db, kind):
    db, tenant_id = quote_db
    result = _create(db, tenant_id, kind)
    assert (result["total"] if kind == "stone" else result.total) == 1440
    assert db.scalar(select(func.count()).select_from(Quote)) == 1
    assert db.scalar(select(func.count()).select_from(ActivityLog)) == 1


@pytest.mark.parametrize("kind", ["stone", "general"])
def test_failed_activity_does_not_leave_a_saved_quote(quote_db, monkeypatch, kind):
    db, tenant_id = quote_db
    def failed_activity(*args, **kwargs):
        raise RuntimeError("synthetic activity write failure")
    monkeypatch.setattr(service.activity_service, "log", failed_activity)
    with pytest.raises(RuntimeError, match="synthetic activity write failure"):
        _create(db, tenant_id, kind)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Quote)) == 0
    assert db.scalar(select(func.count()).select_from(QuoteItem)) == 0


@pytest.mark.parametrize("operation", ["approve", "handoff"])
def test_quote_transition_and_activity_use_one_connection(quote_db, operation):
    db, tenant_id = quote_db
    created = _create(db, tenant_id, "stone")
    if operation == "approve":
        row = service.QuoteService().approve(db, created["id"], tenant_id, uuid4())
        assert row.status == "approved"
    else:
        quote = db.get(Quote, created["id"])
        quote.status = "approved"
        db.commit()
        row = service.QuoteService().handoff(db, created["id"], tenant_id)
        assert row.quote_id == created["id"]
    assert db.scalar(select(func.count()).select_from(ActivityLog)) == 2
