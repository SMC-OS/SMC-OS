"""Sprint 029 — RC manifest generator contract.

The generator itself is deliberately not pointed at real git/Alembic
subprocesses in these tests (same offline-testing convention as
tests/test_staging_scripts.py for scripts/staging/smoke.py) — it exercises
the script's pure, dependency-injected logic and its VERSION-file reading.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCRIPT = PROJECT_ROOT / "scripts" / "release" / "rc_manifest.py"


def load_manifest_module():
    spec = importlib.util.spec_from_file_location("rc_manifest", MANIFEST_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_version_reads_and_strips_the_version_file(tmp_path):
    manifest = load_manifest_module()
    (tmp_path / "VERSION").write_text("1.0.0-rc.1\n", encoding="utf-8")

    assert manifest.read_version(tmp_path) == "1.0.0-rc.1"


def test_read_version_rejects_a_missing_file(tmp_path):
    manifest = load_manifest_module()

    with pytest.raises(FileNotFoundError):
        manifest.read_version(tmp_path)


def test_build_manifest_has_the_locked_contract_shape():
    manifest = load_manifest_module()

    result = manifest.build_manifest(
        version="1.0.0-rc.1",
        git_sha="a" * 40,
        migration_head="2243d66f83da",
        created_at="2026-09-02T00:00:00Z",
    )

    assert result == {
        "rc_version": "1.0.0-rc.1",
        "rc_tag": "v1.0.0-rc.1",
        "git_sha": "a" * 40,
        "migration_head": "2243d66f83da",
        "created_at": "2026-09-02T00:00:00Z",
        "expected_services": ["simo-api-staging", "simo-web-staging"],
        "required_ci_jobs": ["backend", "frontend", "e2e"],
        "expected_smoke_gate_count": 27,
        "rollback_target_sha": "737ac10bcbde682564d3bac6a9a6bb2fda59628f",
    }


def test_build_manifest_rejects_a_non_full_length_git_sha():
    manifest = load_manifest_module()

    with pytest.raises(ValueError):
        manifest.build_manifest(
            version="1.0.0-rc.1",
            git_sha="abc123",
            migration_head="2243d66f83da",
            created_at="2026-09-02T00:00:00Z",
        )


def test_build_manifest_rejects_a_migration_head_other_than_the_locked_value():
    manifest = load_manifest_module()

    with pytest.raises(ValueError):
        manifest.build_manifest(
            version="1.0.0-rc.1",
            git_sha="a" * 40,
            migration_head="deadbeefcafe",
            created_at="2026-09-02T00:00:00Z",
        )


def test_main_writes_the_manifest_as_json(tmp_path, monkeypatch):
    manifest = load_manifest_module()
    (tmp_path / "VERSION").write_text("1.0.0-rc.1\n", encoding="utf-8")
    output_path = tmp_path / "manifest.json"

    monkeypatch.setattr(manifest, "_git_sha", lambda repo_root: "b" * 40)
    monkeypatch.setattr(manifest, "_migration_head", lambda repo_root: "2243d66f83da")
    monkeypatch.setattr(manifest, "_utc_now_iso", lambda: "2026-09-02T00:00:00Z")

    exit_code = manifest.main(["--repo-root", str(tmp_path), "--output", str(output_path)])

    assert exit_code == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["git_sha"] == "b" * 40
    assert written["rc_tag"] == "v1.0.0-rc.1"
