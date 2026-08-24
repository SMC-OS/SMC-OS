from __future__ import annotations

import re
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAILWAY_DIR = PROJECT_ROOT / "deploy" / "railway"


def read_toml(name: str) -> tuple[dict[str, object], str]:
    path = RAILWAY_DIR / name
    text = path.read_text(encoding="utf-8")
    return tomllib.loads(text), text


def test_api_railway_contract_uses_release_command_and_unchanged_image_startup():
    config, text = read_toml("api.railway.toml")

    assert config["build"]["dockerfilePath"] == "Dockerfile"
    assert config["deploy"]["preDeployCommand"] == (
        "python -m app.core.runtime_check && alembic upgrade head && alembic current"
    )
    assert config["deploy"]["healthcheckPath"] == "/health"
    assert config["deploy"]["healthcheckTimeout"] == 300
    assert "startCommand" not in config["deploy"]
    assert "seed" not in text.lower()
    assert "railway_run_uid" not in text.lower()
    assert "railway.app" not in text.lower()
    assert "token" not in text.lower()
    assert ".env" not in text.lower()


def test_web_railway_contract_uses_web_image_and_public_root_healthcheck():
    config, text = read_toml("web.railway.toml")

    assert config["build"]["dockerfilePath"] == "apps/web/Dockerfile"
    assert config["deploy"]["healthcheckPath"] == "/"
    assert config["deploy"]["healthcheckTimeout"] == 300
    assert "startCommand" not in config["deploy"]
    assert "seed" not in text.lower()
    assert "alembic" not in text.lower()
    assert "railway_run_uid" not in text.lower()
    assert "railway.app" not in text.lower()
    assert "token" not in text.lower()
    assert ".env" not in text.lower()


def test_staging_environment_inventory_is_complete_and_secret_free():
    text = (RAILWAY_DIR / "staging.env.example").read_text(encoding="utf-8")

    required = {
        "APP_ENV=production",
        "PORT=8000",
        "DATABASE_URL=${{simo-postgres-staging.DATABASE_URL}}",
        "JWT_SECRET_KEY=<set-as-a-Railway-sealed-secret>",
        "JWT_ALGORITHM=HS256",
        "JWT_EXPIRE_MINUTES=60",
        "SEED_ADMIN_EMAIL=<set-as-a-Railway-sealed-secret>",
        "SEED_ADMIN_PASSWORD=<set-as-a-Railway-sealed-secret>",
        "SEED_DATA_ENABLED=false",
        "CORS_ALLOWED_ORIGINS=https://${{simo-web-staging.RAILWAY_PUBLIC_DOMAIN}}",
        "READINESS_TIMEOUT_SECONDS=2",
        "UPLOAD_DIR=/var/lib/simo-os/uploads",
        "NEXT_PUBLIC_API_URL=https://${{simo-api-staging.RAILWAY_PUBLIC_DOMAIN}}",
    }
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    assert required <= lines
    assert "DATABASE_URL=${{simo-postgres-staging.DATABASE_URL}}" in lines
    assert not re.search(r"(?i)(password|secret|token|api[_-]?key)\s*=\s*(?!<)[^\s#]+", text)
    assert "postgres://" not in text.lower()
    assert "postgresql://" not in text.lower()


def test_frontend_section_explicitly_sets_production_runtime_mode():
    text = (RAILWAY_DIR / "staging.env.example").read_text(encoding="utf-8")
    frontend_section = text.split("# Frontend build and runtime variables", maxsplit=1)[1]

    assert "APP_ENV=production" in frontend_section
