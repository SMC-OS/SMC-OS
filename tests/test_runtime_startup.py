"""Lifecycle tests for the Sprint 018 runtime startup boundary."""

import ast
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppEnvironment, Settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_development(**values: object) -> Settings:
    return Settings(_env_file=None, app_env=AppEnvironment.DEVELOPMENT, **values)


def make_production(**values: object) -> Settings:
    defaults = {
        "app_env": AppEnvironment.PRODUCTION,
        "database_url": "postgresql+psycopg://simo:strong-password@db.internal/simo_os",
        "jwt_secret_key": "x" * 32,
        "seed_admin_email": "bootstrap@example.invalid",
        "seed_admin_password": "safe-bootstrap-password",
        "seed_data_enabled": False,
        "cors_allowed_origins": ["https://app.example.com"],
        "upload_dir": "/var/lib/simo-os/uploads",
    }
    return Settings(_env_file=None, **(defaults | values))


def test_development_creates_missing_upload_directory(tmp_path):
    from app.core.startup import prepare_upload_directory

    target = tmp_path / "new-uploads"

    result = prepare_upload_directory(make_development(upload_dir=str(target)))

    assert result == target.resolve()
    assert target.is_dir()


def test_production_requires_existing_writable_mount(tmp_path):
    from app.core.startup import prepare_upload_directory

    target = tmp_path / "missing"

    with pytest.raises(RuntimeError, match="UPLOAD_DIR"):
        prepare_upload_directory(make_production(upload_dir=str(target)))

    assert not target.exists()


def test_production_rejects_non_writable_mount_without_touching_existing_documents(
    tmp_path, monkeypatch
):
    from app.core import startup

    target = tmp_path / "mounted-uploads"
    target.mkdir()
    document = target / "existing-document.txt"
    document.write_text("keep me", encoding="utf-8")
    original_open = Path.open

    def deny_probe(path: Path, *args, **kwargs):
        if path.parent == target and path.name.startswith(".simo-os-write-probe-"):
            raise PermissionError("read-only mount")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_probe)

    with pytest.raises(RuntimeError, match="UPLOAD_DIR"):
        startup.prepare_upload_directory(make_production(upload_dir=str(target)))

    assert document.read_text(encoding="utf-8") == "keep me"
    assert list(target.glob(".simo-os-write-probe-*")) == []


def test_production_rejects_mount_when_probe_cleanup_fails(tmp_path, monkeypatch):
    from app.core import startup

    target = tmp_path / "mounted-uploads"
    target.mkdir()
    document = target / "existing-document.txt"
    document.write_text("keep me", encoding="utf-8")
    original_unlink = Path.unlink

    def deny_probe_cleanup(path: Path, *args, **kwargs):
        if path.parent == target and path.name.startswith(".simo-os-write-probe-"):
            raise PermissionError("cannot remove probe")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_probe_cleanup)

    with pytest.raises(RuntimeError, match="UPLOAD_DIR"):
        startup.prepare_upload_directory(make_production(upload_dir=str(target)))

    assert document.read_text(encoding="utf-8") == "keep me"
    probes = list(target.glob(".simo-os-write-probe-*"))
    assert len(probes) == 1
    original_unlink(probes[0])


def test_development_invokes_every_seeder_once():
    from app.core.startup import run_seeders

    seeders = tuple(Mock() for _ in range(4))

    run_seeders(make_development(seed_data_enabled=True), seeders)

    assert [fn.call_count for fn in seeders] == [1, 1, 1, 1]


def test_disabled_seeding_invokes_nothing():
    from app.core.startup import run_seeders

    seeders = tuple(Mock() for _ in range(4))

    run_seeders(make_development(seed_data_enabled=False), seeders)

    assert [fn.call_count for fn in seeders] == [0, 0, 0, 0]


def test_safe_production_configuration_invokes_no_seeders():
    from app.core.startup import run_seeders

    seeders = tuple(Mock() for _ in range(4))

    run_seeders(make_production(), seeders)

    assert [fn.call_count for fn in seeders] == [0, 0, 0, 0]


def test_lifespan_runs_initialization_before_serving(monkeypatch, tmp_path):
    from app.core import startup
    from app.main import create_app

    configured = make_development(upload_dir=str(tmp_path / "uploads"))
    prepare = Mock(return_value=tmp_path / "uploads")
    seed = Mock()
    monkeypatch.setattr(startup, "prepare_upload_directory", prepare)
    monkeypatch.setattr(startup, "run_seeders", seed)

    application = create_app(configured)

    assert prepare.call_count == 0
    assert seed.call_count == 0
    with TestClient(application) as client:
        assert prepare.call_count == 1
        assert seed.call_count == 1
        assert client.get("/health").status_code == 200


def test_main_import_does_not_call_seeders_in_a_fresh_process():
    code = """
from unittest.mock import patch
with (
    patch('app.activity.seed.seed_activity', side_effect=AssertionError('seed activity')),
    patch('app.notifications.seed.seed_notifications', side_effect=AssertionError('seed notifications')),
    patch('app.auth.seed.seed_users', side_effect=AssertionError('seed users')),
    patch('app.materials.seed.seed_materials', side_effect=AssertionError('seed materials')),
):
    import app.main
"""
    environment = os.environ.copy()
    environment["APP_ENV"] = "development"

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_lifespan_failure_prevents_the_application_from_serving(monkeypatch, tmp_path):
    from app.core import startup
    from app.main import create_app

    monkeypatch.setattr(
        startup,
        "prepare_upload_directory",
        Mock(side_effect=RuntimeError("mount unavailable")),
    )
    application = create_app(make_development(upload_dir=str(tmp_path / "uploads")))

    with pytest.raises(RuntimeError, match="mount unavailable"):
        with TestClient(application):
            pytest.fail("The application served a request after startup failed")


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


@pytest.mark.parametrize("relative_path", ["app/core/startup.py", "app/main.py"])
def test_startup_modules_do_not_import_or_call_alembic_or_subprocess(relative_path):
    tree = ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] not in {"alembic", "subprocess"} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or node.module.split(".")[0] not in {"alembic", "subprocess"}
        elif isinstance(node, ast.Call):
            qualified_name = _qualified_name(node.func)
            assert qualified_name is None or not qualified_name.startswith("alembic.")


def test_production_dockerfile_enforces_the_backend_runtime_contract():
    """Sprint 033 (ADR-035) supersedes part of this contract: the image's
    default CMD now runs the migration gate (app/core/migrate_gate.py)
    before exec'ing uvicorn, rather than starting uvicorn directly — see
    docs/SPRINTS/sprint-033.md §1.2/§2.1 for why (Railway's separate
    preDeployCommand release-job step proved unreliable via `railway
    up`). The Dockerfile itself still never spells out an `alembic`
    invocation directly (that stays inside migrate_gate.py, the single
    place the command is invoked, independently tested) and ENTRYPOINT
    is still not used — `exec` inside a plain CMD keeps PID 1 handling
    identical to the previous shape.
    """
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    normalized = dockerfile.lower()

    assert "from python:3.12-slim" in normalized
    assert "user simo" in normalized
    assert "expose 8000" in normalized
    assert "app.core.migrate_gate" in normalized
    assert "exec uvicorn app.main:app" in normalized
    assert "--no-access-log" in normalized
    assert "/health" in normalized

    assert "entrypoint" not in normalized
    assert "alembic upgrade" not in normalized
    assert "alembic downgrade" not in normalized
    assert "copy .env" not in normalized
    assert "seed_" not in normalized
    assert "seed-data" not in normalized


def test_migrate_gate_is_the_only_module_invoking_alembic_upgrade():
    """The Dockerfile delegates to exactly one script for the actual
    `alembic upgrade` invocation — keeps the migration command in one
    place, independently testable, matching the module's own contract
    (see test_migrate_gate.py)."""
    gate_source = (PROJECT_ROOT / "app" / "core" / "migrate_gate.py").read_text(encoding="utf-8")
    assert '"alembic", "upgrade", "head"' in gate_source


def test_docker_build_context_excludes_local_and_sensitive_files():
    ignored = {
        line.strip().rstrip("/").lower()
        for line in (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {
        ".env",
        ".git",
        ".venv",
        "node_modules",
        "uploads",
        ".agents",
        ".claude",
    } <= ignored
