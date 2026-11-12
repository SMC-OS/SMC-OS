"""The synthetic-owner provisioner must run on staging and the isolated QA environment (where
APP_ENV is "production" by design) and must still refuse the real production environment."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("provision", Path(__file__).resolve().parents[1] / "scripts/qa/provision_synthetic_owner.py")
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)

DB = "postgresql+psycopg://u:p@postgres.railway.internal:5432/railway"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_NAME"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "railway_env,project,expected",
    [
        ("staging", "simo-os", "staging"),
        ("acceptance", "geocore-qa-20261110", "acceptance"),
        ("production", "simo-os", "production"),
        ("acceptance", "some-other-project", "unknown"),  # the QA name alone is not enough
        ("preview", "geocore-qa-20261110", "unknown"),
    ],
)
def test_railway_identity_decides_even_though_app_env_is_production(monkeypatch, railway_env, project, expected):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", railway_env)
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", project)
    assert provision.detected_environment(DB, "production") == expected


def test_off_railway_behaviour_is_unchanged():
    assert provision.detected_environment("postgresql+psycopg://u:p@localhost/x", "development") == "local"
    assert provision.detected_environment("postgresql+psycopg://u:p@localhost/x", "production") == "production"
    assert provision.detected_environment(DB, "development") == "unknown"


def test_acceptance_is_a_selectable_confirmation_and_production_is_not():
    source = (Path(provision.__file__)).read_text()
    assert 'choices=["staging", "acceptance", "local"]' in source


def test_idempotent_flag_is_supported_and_exists_in_the_cli():
    source = Path(provision.__file__).read_text()
    assert '"--idempotent"' in source and "EmailAlreadyRegisteredError" in source


def test_provisioner_is_idempotent_verifies_login_and_survives_newline_polluted_inputs(monkeypatch, capsys):
    """Real database. The same shape the QA pre-deploy step uses: run twice, verify the login, reject a wrong password."""
    import uuid
    from sqlalchemy import delete
    from app.database.database import SessionLocal
    from app.database.models import Tenant, User

    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "acceptance")
    monkeypatch.setenv("RAILWAY_PROJECT_NAME", "geocore-qa-20261110")
    tag = uuid.uuid4().hex[:8]
    email, password = f"prov-{tag}@acceptance.invalid", f"Prov-{tag}-Pass-0123456789Aa1!"
    monkeypatch.setenv("SYNTHETIC_OWNER_PASSWORD", password)
    args = ["--email", email, "--company", f"Prov {tag}", "--confirm-environment", "acceptance", "--idempotent", "--verify-login"]
    try:
        assert provision.main(args) == 0
        assert provision.main(args) == 0  # a repeat must not fail a later redeploy
        out = capsys.readouterr().out
        assert "provisioned tenant" in out and "already provisioned" in out and out.count("verified:") == 2
        monkeypatch.setenv("SYNTHETIC_OWNER_PASSWORD", "Wrong-Pass-000000000000Aa1!")
        assert provision.main(args) == 3  # credentials that do not authenticate must fail loudly
    finally:
        db = SessionLocal()
        try:
            from sqlalchemy import text

            users = db.query(User).filter(User.email == email).all()
            tenant_ids = [str(u.tenant_id) for u in users]
            user_ids = [str(u.id) for u in users]
            # Signup writes activity, a trial subscription, verification tokens and communications: remove them first.
            for table, column, ids in (
                ("activity_log", "tenant_id", tenant_ids), ("subscriptions", "tenant_id", tenant_ids),
                ("notifications", "tenant_id", tenant_ids), ("communications", "tenant_id", tenant_ids),
                ("email_verification_tokens", "user_id", user_ids),
            ):
                for value in ids:
                    try:
                        db.execute(text(f"DELETE FROM {table} WHERE {column} = :v"), {"v": value})
                        db.commit()
                    except Exception:
                        db.rollback()
            db.execute(delete(User).where(User.email == email))
            if tenant_ids:
                db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
            db.commit()
        finally:
            db.close()
