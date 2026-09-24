"""Safety guard of scripts/staging/verify_password_byte_limit.py.

The verifier writes synthetic accounts, so it must only ever run in the
staging container against the staging database. It must NOT rely on
APP_ENV: the staging runbook sets APP_ENV=production on staging.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app.core.config import AppEnvironment, settings
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Tenant

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "staging" / "verify_password_byte_limit.py"
STAGING_HOST_URL = "postgresql+psycopg://u:p@postgres.railway.internal:5432/railway"
PRODUCTION_HOST_URL = "postgresql+psycopg://u:p@simo-postgres-production.railway.internal:5432/railway"


def _load():
    spec = importlib.util.spec_from_file_location("verify_password_byte_limit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------- pure decision


def test_staging_is_accepted():
    assert _load().safety_refusal("staging", "postgres.railway.internal", False) is None


def test_production_environment_is_refused():
    assert "production" in _load().safety_refusal("production", "postgres.railway.internal", False)


def test_production_database_host_is_refused():
    reason = _load().safety_refusal("staging", "simo-postgres-production.railway.internal", False)
    assert reason and "production database" in reason


def test_production_database_host_is_refused_case_insensitively():
    assert _load().safety_refusal("staging", "SIMO-POSTGRES-PRODUCTION.railway.internal", False)


def test_production_sales_tenant_is_refused():
    reason = _load().safety_refusal("staging", "postgres.railway.internal", True)
    assert reason and "production sales workspace" in reason


@pytest.mark.parametrize("name", [None, "", "   ", "development", "Staging", "staging-2", "pr-12"])
def test_missing_or_unknown_environment_is_refused(name):
    assert _load().safety_refusal(name, "postgres.railway.internal", False)


# ------------------------------------------- against a real database


def test_staging_with_app_env_production_is_accepted(monkeypatch):
    """The exact staging configuration: Railway says staging, the runbook
    sets APP_ENV=production. The guard must let it run."""
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setattr(settings, "app_env", AppEnvironment.PRODUCTION)
    db = SessionLocal()
    try:
        assert _load().environment_refusal(db) is None
    finally:
        db.close()


def test_production_host_is_refused_before_connecting(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setattr(settings, "database_url", PRODUCTION_HOST_URL)

    class NoQuery:
        def execute(self, *args, **kwargs):
            raise AssertionError("must not query a production database")

    assert "production database" in _load().environment_refusal(NoQuery())


def test_production_sales_tenant_in_the_database_is_refused(monkeypatch):
    module = _load()
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    db = SessionLocal()
    try:
        existing = db.get(Tenant, uuid.UUID(module.PRODUCTION_SALES_TENANT_ID))
        created = existing is None
        if created:
            db.add(Tenant(id=uuid.UUID(module.PRODUCTION_SALES_TENANT_ID), name="Pytest Prod Marker", slug=f"pytest-prod-marker-{uuid.uuid4().hex[:6]}"))
            db.commit()
        try:
            assert "production sales workspace" in module.environment_refusal(db)
        finally:
            if created:
                db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == uuid.UUID(module.PRODUCTION_SALES_TENANT_ID)))
                db.execute(delete(Tenant).where(Tenant.id == uuid.UUID(module.PRODUCTION_SALES_TENANT_ID)))
                db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("name", [None, "production", "development"])
def test_main_refuses_and_writes_nothing(monkeypatch, capsys, name):
    if name is None:
        monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    else:
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", name)
    module = _load()
    assert module.main(["--confirm-staging"]) == 2
    out = capsys.readouterr().out
    assert out.startswith("Refusing to run:")
    assert "postgresql" not in out and "@" not in out
    db = SessionLocal()
    try:
        assert db.scalars(select(Tenant).where(Tenant.name.like(f"{module.PREFIX}%"))).first() is None
    finally:
        db.close()


def test_main_refuses_without_confirmation(capsys):
    assert _load().main([]) == 2
    assert "--confirm-staging" in capsys.readouterr().out


def test_refusal_messages_never_contain_credentials(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setattr(settings, "database_url", PRODUCTION_HOST_URL)
    db = SessionLocal()
    try:
        reason = _load().environment_refusal(db)
    finally:
        db.close()
    assert "u:p" not in reason and "postgresql" not in reason
