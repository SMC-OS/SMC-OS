"""Public estimates remain public; tenant writes enforce workspace access."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import DateTime, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.api.v1 import core
from app.auth.security import create_access_token
from app.database.database import get_db
from app.database.models import ActivityLog, Customer, Material, Project, Quote, QuoteItem, RevokedBrowserSession, Subscription, Tenant, User
from app.quotes.service import automation_dispatcher


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
def public_quote_api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'access.db'}")
    for model in (Tenant, User, RevokedBrowserSession, Subscription, Customer, Material, Project, Quote, QuoteItem, ActivityLog):
        model.__table__.create(engine)
    api = FastAPI()
    api.include_router(core.router, prefix="/api/v1")

    class AccessSession(Session):
        pass

    @event.listens_for(AccessSession, "loaded_as_persistent")
    def restore_sqlite_timezone(db, row):
        # SQLite discards DateTime(timezone=True); PostgreSQL retains UTC.
        for column in row.__table__.columns:
            value = getattr(row, column.name)
            if isinstance(column.type, DateTime) and column.type.timezone and value is not None and value.tzinfo is None:
                setattr(row, column.name, value.replace(tzinfo=timezone.utc))

    def session():
        with AccessSession(engine) as db:
            yield db

    api.dependency_overrides[get_db] = session
    # Parsing and automation have their own suites. Keep the actual routes,
    # JWT validation, verification/billing guards and persistence here.
    monkeypatch.setattr(core.estimator, "parse", lambda text: _quote_body())
    monkeypatch.setattr(automation_dispatcher, "dispatch_quote_created", lambda *a: None)
    with TestClient(api) as client:
        yield client, engine
    engine.dispose()


def _quote_body():
    return {"customer": "Synthetic access test", "site_address_line1": "1 Test Street",
            "postcode": "NW2 7RP", "pricing_mode": "manual", "manual_price": 1200,
            "items": [{"material": "Synthetic quartz", "thickness": "20mm", "length_mm": 2000}]}


def _identity(engine, state):
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        tenant = Tenant(name="Access test", slug="access-test")
        db.add(tenant)
        db.flush()
        user = User(tenant_id=tenant.id, name="Synthetic Owner", email="access@example.invalid",
                    password_hash="unused-synthetic-hash", role="Owner", created_at=now,
                    email_verified_at=None if state == "unverified" else now)
        db.add(user)
        if state != "no_subscription":
            db.add(Subscription(tenant_id=tenant.id, plan="pro", billing_period="monthly",
                                status=state if state in {"active", "past_due", "cancelled", "incomplete"} else "trialing",
                                legacy_grandfathered=state == "complimentary",
                                trial_start=now - timedelta(days=15),
                                trial_end=now + timedelta(days=1) if state != "expired" else now - timedelta(days=1)))
        db.commit()
        return {"Authorization": "Bearer " + create_access_token(str(user.id), str(tenant.id))}


@pytest.mark.parametrize("route", ["quote", "estimate", "dashboard"])
@pytest.mark.parametrize("state,expected", [
    ("unverified", 403), ("expired", 402), ("no_subscription", 402),
    ("past_due", 402), ("cancelled", 402), ("incomplete", 402),
    ("trialing", 200), ("active", 200), ("complimentary", 200),
])
def test_authenticated_quote_writes_obey_workspace_access(public_quote_api, route, state, expected):
    client, engine = public_quote_api
    headers = _identity(engine, state)
    response = (client.get("/api/v1/dashboard", headers=headers) if route == "dashboard" else
                client.post("/api/v1/" + route, headers=headers,
                            json=_quote_body() if route == "quote" else {"text": "Synthetic estimate"}))
    assert response.status_code == expected
    with Session(engine) as db:
        writes = 1 if expected == 200 and route != "dashboard" else 0
        assert db.scalar(select(func.count()).select_from(Quote)) == writes
        assert db.scalar(select(func.count()).select_from(ActivityLog)) == writes


@pytest.mark.parametrize("route", ["quote", "estimate"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-public-token"}])
def test_anonymous_estimates_keep_the_existing_public_contract(public_quote_api, monkeypatch, route, headers):
    client, engine = public_quote_api
    with Session(engine) as db:
        db.add(Material(name="Synthetic quartz", thickness="20mm", price=1200))
        db.commit()
    body = _quote_body()
    body.pop("pricing_mode")
    body.pop("manual_price")
    if route == "estimate":
        # The public parser yields a catalogue request, never manual pricing.
        monkeypatch.setattr(core.estimator, "parse", lambda text: body)
    response = client.post("/api/v1/" + route, headers=headers,
                           json=body if route == "quote" else {"text": "Synthetic estimate"})
    assert response.status_code == 200
    with Session(engine) as db:
        quote = db.scalars(select(Quote)).one()
        assert quote.tenant_id is None
        assert db.scalars(select(ActivityLog)).one().tenant_id is None
