"""Launch hardening: interactive API documentation is not served in production.

/docs, /redoc and /openapi.json publish the full route map of a public API and
nothing in the product consumes them, so production (APP_ENV=production, which
Railway staging also sets) must answer 404 for all three, while development and
test keep them. The health endpoints and the API itself are unaffected.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppEnvironment, Settings
from app.main import create_app

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def make_settings(app_env: AppEnvironment, upload_dir: Path) -> Settings:
    if app_env is AppEnvironment.PRODUCTION:
        return Settings(
            _env_file=None,
            app_env=app_env,
            database_url="postgresql+psycopg://simo:strong-password@db.internal/simo_os",
            jwt_secret_key="x" * 32,
            seed_admin_email="bootstrap@example.invalid",
            seed_admin_password="safe-bootstrap-password",
            seed_data_enabled=False,
            cors_allowed_origins=["https://app.example.com"],
            upload_dir=str(upload_dir),
        )
    return Settings(_env_file=None, app_env=app_env, cors_allowed_origins=["https://allowed.example"])


def test_production_disables_docs_redoc_and_openapi(tmp_path):
    application = create_app(make_settings(AppEnvironment.PRODUCTION, tmp_path))

    assert application.docs_url is None
    assert application.redoc_url is None
    assert application.openapi_url is None

    client = TestClient(application)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404, path


@pytest.mark.parametrize("app_env", [AppEnvironment.DEVELOPMENT, AppEnvironment.TEST])
def test_non_production_keeps_docs_redoc_and_openapi(app_env, tmp_path):
    application = create_app(make_settings(app_env, tmp_path))

    assert (application.docs_url, application.redoc_url, application.openapi_url) == (
        "/docs",
        "/redoc",
        "/openapi.json",
    )
    client = TestClient(application)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 200, path


def test_production_still_serves_the_unversioned_infra_routes(tmp_path):
    client = TestClient(create_app(make_settings(AppEnvironment.PRODUCTION, tmp_path)))

    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200


def test_api_docs_flag_follows_app_env_only(tmp_path):
    assert make_settings(AppEnvironment.PRODUCTION, tmp_path).api_docs_enabled is False
    assert make_settings(AppEnvironment.DEVELOPMENT, tmp_path).api_docs_enabled is True
    assert make_settings(AppEnvironment.TEST, tmp_path).api_docs_enabled is True


def test_nothing_in_the_product_consumes_the_docs_endpoints():
    """If this ever fails, a feature started depending on /openapi.json and the
    production hardening needs revisiting before it ships."""
    root = Path(__file__).resolve().parents[1]
    needles = ("openapi.json", "/redoc")
    # The two files that define the policy name the paths by design.
    defining_files = {root / "app" / "main.py", root / "app" / "core" / "config.py"}
    offenders = []
    for base in ("app", "apps/web/app", "apps/web/components", "apps/web/lib", "apps/marketing"):
        for path in (root / base).rglob("*"):
            if path in defining_files or path.suffix not in {".py", ".ts", ".tsx", ".mjs", ".js"} or "node_modules" in path.parts or ".next" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(needle in text for needle in needles):
                offenders.append(str(path.relative_to(root)))
    assert offenders == [], offenders
