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
