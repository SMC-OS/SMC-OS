"""Sprint 029 — generates the Release Candidate manifest (Phase 11).

Reads VERSION, the current git SHA, and the current Alembic migration head,
and writes the fixed manifest shape the Sprint 029 locked contract requires
(docs/SPRINTS/sprint-029.md). This is a repository-only artifact — it does
not change application runtime behavior and is not read by the running
service.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


LOCKED_MIGRATION_HEAD = "2243d66f83da"
ROLLBACK_TARGET_SHA = "737ac10bcbde682564d3bac6a9a6bb2fda59628f"
EXPECTED_SERVICES = ["simo-api-staging", "simo-web-staging"]
REQUIRED_CI_JOBS = ["backend", "frontend", "e2e"]
EXPECTED_SMOKE_GATE_COUNT = 27


def read_version(repo_root: Path) -> str:
    version_file = repo_root / "VERSION"
    if not version_file.is_file():
        raise FileNotFoundError(f"VERSION file not found at {version_file}")
    return version_file.read_text(encoding="utf-8").strip()


def build_manifest(
    *, version: str, git_sha: str, migration_head: str, created_at: str
) -> dict[str, object]:
    if len(git_sha) != 40 or not all(c in "0123456789abcdef" for c in git_sha.lower()):
        raise ValueError(f"git_sha must be a full 40-character hex SHA, got {git_sha!r}")
    if migration_head != LOCKED_MIGRATION_HEAD:
        raise ValueError(
            f"migration_head must equal the locked value {LOCKED_MIGRATION_HEAD!r}, "
            f"got {migration_head!r} — Sprint 029 ships no migration"
        )
    return {
        "rc_version": version,
        "rc_tag": f"v{version}",
        "git_sha": git_sha,
        "migration_head": migration_head,
        "created_at": created_at,
        "expected_services": EXPECTED_SERVICES,
        "required_ci_jobs": REQUIRED_CI_JOBS,
        "expected_smoke_gate_count": EXPECTED_SMOKE_GATE_COUNT,
        "rollback_target_sha": ROLLBACK_TARGET_SHA,
    }


def _git_sha(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
    ).strip()


def _migration_head(repo_root: Path) -> str:
    output = subprocess.check_output(
        ["alembic", "heads"], cwd=repo_root, text=True
    ).strip()
    # "2243d66f83da (head)" -> "2243d66f83da"
    return output.split()[0]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    manifest = build_manifest(
        version=read_version(repo_root),
        git_sha=_git_sha(repo_root),
        migration_head=_migration_head(repo_root),
        created_at=_utc_now_iso(),
    )
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
