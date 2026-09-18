import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import AppEnvironment, Settings


def make_settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_development_defaults_remain_convenient():
    configured = make_settings()

    assert configured.app_env is AppEnvironment.DEVELOPMENT
    assert configured.seed_data_enabled is True
    assert configured.cors_allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Sprint 041 — apps/marketing's dev server now calls the API
        # directly (GET /billing/plans, POST /demo-requests).
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]


def test_unknown_app_environment_is_rejected():
    with pytest.raises(ValidationError):
        make_settings(app_env="staging")


@pytest.mark.parametrize("value", ["development", "test", "production"])
def test_known_app_environments_are_parsed(value):
    values = SAFE_PRODUCTION if value == "production" else {"app_env": value}
    configured = make_settings(**values)

    assert configured.app_env.value == value


def test_cors_origins_are_parsed_from_a_comma_separated_string():
    configured = make_settings(
        cors_allowed_origins=" https://app.example.com,https://admin.example.com "
    )

    assert configured.cors_allowed_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_cors_origins_reject_empty_entries():
    with pytest.raises(ValidationError):
        make_settings(cors_allowed_origins="https://app.example.com, ")


SAFE_PRODUCTION = {
    "app_env": "production",
    "database_url": "postgresql+psycopg://simo:strong-password@db.internal/simo_os",
    "jwt_secret_key": "x" * 32,
    "seed_admin_email": "bootstrap@example.invalid",
    "seed_admin_password": "safe-bootstrap-password",
    "seed_data_enabled": False,
    "cors_allowed_origins": ["https://app.example.com"],
    "upload_dir": "/var/lib/simo-os/uploads",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_runtime_check(values: dict[str, object]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": str(values["app_env"]),
            "DATABASE_URL": str(values["database_url"]),
            "JWT_SECRET_KEY": str(values["jwt_secret_key"]),
            "SEED_ADMIN_EMAIL": str(values["seed_admin_email"]),
            "SEED_ADMIN_PASSWORD": str(values["seed_admin_password"]),
            "SEED_DATA_ENABLED": str(values["seed_data_enabled"]).lower(),
            "CORS_ALLOWED_ORIGINS": ",".join(values["cors_allowed_origins"]),
            "UPLOAD_DIR": str(values["upload_dir"]),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "app.core.runtime_check"],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_production_accepts_a_complete_safe_configuration():
    configured = make_settings(**SAFE_PRODUCTION)

    assert configured.app_env is AppEnvironment.PRODUCTION


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("jwt_secret_key", "dev-only-insecure-secret-change-me"),
        ("jwt_secret_key", "short"),
        ("seed_admin_email", "owner@geocore.local"),
        # Sprint 034 (Phase 2) — the pre-rebrand default must stay rejected;
        # a production environment that still carries it is exactly as unsafe
        # as it was before the rename.
        ("seed_admin_email", "owner@simo-os.local"),
        ("seed_admin_password", "change-me-on-first-login"),
        ("seed_data_enabled", True),
        ("cors_allowed_origins", []),
        ("cors_allowed_origins", ["*"]),
        ("cors_allowed_origins", ["http://app.example.com"]),
        ("cors_allowed_origins", ["https://app.example.com/path"]),
        ("database_url", "postgresql+psycopg://simo:simo@localhost:5432/simo_os"),
        ("upload_dir", "./uploads"),
    ],
)
def test_production_rejects_unsafe_configuration(field, value):
    values = {**SAFE_PRODUCTION, field: value}

    with pytest.raises(ValidationError):
        make_settings(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("jwt_secret_key", "  dev-only-insecure-secret-change-me  "),
        ("seed_admin_email", "  owner@geocore.local  "),
        ("seed_admin_email", "  owner@simo-os.local  "),
        ("seed_admin_password", "  change-me-on-first-login  "),
    ],
)
def test_production_rejects_whitespace_padded_development_defaults(field, value):
    with pytest.raises(ValidationError):
        make_settings(**{**SAFE_PRODUCTION, field: value})


@pytest.mark.parametrize(
    "origins",
    [
        ["app.example.com"],
        ["https://"],
        ["https://app.example.com?next=/"],
        ["https://app.example.com#section"],
        ["https://user:password@app.example.com"],
    ],
)
def test_production_cors_entries_must_be_https_origins_with_a_host(origins):
    with pytest.raises(ValidationError):
        make_settings(**{**SAFE_PRODUCTION, "cors_allowed_origins": origins})


@pytest.mark.parametrize("value", [0, -0.1, 2.01, 10])
def test_readiness_timeout_must_be_positive_and_at_most_two_seconds(value):
    with pytest.raises(ValidationError):
        make_settings(**{**SAFE_PRODUCTION, "readiness_timeout_seconds": value})


def test_readiness_timeout_accepts_the_two_second_maximum():
    configured = make_settings(**{**SAFE_PRODUCTION, "readiness_timeout_seconds": 2.0})

    assert configured.readiness_timeout_seconds == 2.0


def test_production_validation_error_does_not_include_the_jwt_secret():
    supplied_secret = "redact-me-short-secret"

    with pytest.raises(ValidationError) as exc_info:
        make_settings(**{**SAFE_PRODUCTION, "jwt_secret_key": supplied_secret})

    assert supplied_secret not in str(exc_info.value)


def test_runtime_check_rejects_unsafe_configuration_without_printing_secrets():
    supplied_secret = "redact-me-short-secret"
    result = run_runtime_check({**SAFE_PRODUCTION, "jwt_secret_key": supplied_secret})

    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr
    assert supplied_secret not in result.stderr


def test_runtime_check_prints_a_sanitized_production_summary():
    result = run_runtime_check(SAFE_PRODUCTION)

    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["app_env"] == "production"
    assert summary["cors_origin_count"] == 1
    assert summary["seed_data_enabled"] is False
    assert SAFE_PRODUCTION["jwt_secret_key"] not in result.stdout
    assert SAFE_PRODUCTION["seed_admin_password"] not in result.stdout
