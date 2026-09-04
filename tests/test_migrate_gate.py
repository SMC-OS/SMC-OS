"""app/core/migrate_gate.py — Sprint 033, Workstream B.

Runtime-check and alembic invocations are mocked (subprocess.run) so
these tests exercise the gate's own control flow (fail-closed ordering,
advisory-lock acquire/release) without needing a real failing migration
to reproduce. The advisory-lock acquire/release itself is exercised for
real against the local Postgres — proving two concurrent callers really
do serialize rather than race.
"""

import threading
from unittest.mock import MagicMock, patch

from app.core.migrate_gate import main, run_migration_under_lock, run_runtime_check
from app.database.database import SessionLocal


def _fake_completed(returncode: int) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    return result


def test_runtime_check_failure_short_circuits_before_migration():
    with (
        patch("app.core.migrate_gate.run_runtime_check", return_value=1) as check,
        patch("app.core.migrate_gate.run_migration_under_lock") as migrate,
    ):
        code = main()

    assert code == 1
    check.assert_called_once()
    migrate.assert_not_called()


def test_migration_failure_after_successful_check_propagates_nonzero():
    with (
        patch("app.core.migrate_gate.run_runtime_check", return_value=0),
        patch("app.core.migrate_gate.run_migration_under_lock", return_value=1),
    ):
        code = main()

    assert code == 1


def test_success_returns_zero():
    with (
        patch("app.core.migrate_gate.run_runtime_check", return_value=0),
        patch("app.core.migrate_gate.run_migration_under_lock", return_value=0),
    ):
        code = main()

    assert code == 0


def test_run_migration_under_lock_invokes_alembic_upgrade_head():
    fake_upgrade = _fake_completed(0)
    fake_current = _fake_completed(0)
    with patch("app.core.migrate_gate.subprocess.run", side_effect=[fake_upgrade, fake_current]) as run:
        code = run_migration_under_lock()

    assert code == 0
    first_call_args = run.call_args_list[0].args[0]
    assert first_call_args == ["alembic", "upgrade", "head"]


def test_run_migration_under_lock_propagates_alembic_failure_and_still_unlocks():
    fake_failure = _fake_completed(1)
    with patch("app.core.migrate_gate.subprocess.run", return_value=fake_failure):
        code = run_migration_under_lock()

    assert code == 1

    # The lock must have been released even on failure — a second call
    # should be able to acquire it immediately rather than hang.
    with patch("app.core.migrate_gate.subprocess.run", return_value=_fake_completed(0)):
        second_code = run_migration_under_lock()
    assert second_code == 0


def test_runtime_check_invokes_the_module_as_a_subprocess():
    with patch("app.core.migrate_gate.subprocess.run", return_value=_fake_completed(0)) as run:
        code = run_runtime_check()

    assert code == 0
    args = run.call_args.args[0]
    assert args[1:] == ["-m", "app.core.runtime_check"]


def test_advisory_lock_really_serializes_concurrent_callers():
    """Two real DB sessions both try to hold the gate's advisory lock at
    once — the second must genuinely block until the first releases it,
    proving the lock (not just the Python code path) is what makes
    concurrent migration attempts safe. Synchronized on explicit events
    rather than sleep timing, so this can't pass by lucky scheduling."""
    from sqlalchemy import text

    from app.core.migrate_gate import _ADVISORY_LOCK_KEY

    acquired_first = threading.Event()
    release_first = threading.Event()
    acquired_second = threading.Event()

    def hold_lock_first():
        db = SessionLocal()
        try:
            db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            acquired_first.set()
            release_first.wait(timeout=5)
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            db.close()

    def hold_lock_second():
        acquired_first.wait(timeout=5)
        db = SessionLocal()
        try:
            db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            acquired_second.set()
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            db.close()

    t1 = threading.Thread(target=hold_lock_first)
    t2 = threading.Thread(target=hold_lock_second)
    t1.start()
    assert acquired_first.wait(timeout=5), "first caller never acquired the lock"
    t2.start()

    # The second caller must still be blocked a moment after the first
    # has the lock — this is the actual serialization proof.
    assert not acquired_second.wait(timeout=0.5), "second caller acquired the lock while the first still held it"

    release_first.set()
    assert acquired_second.wait(timeout=5), "second caller never acquired the lock after release"

    t1.join(timeout=5)
    t2.join(timeout=5)
