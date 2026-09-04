"""Migration gate — Sprint 033, Workstream B.

Sprint 032 found that Railway's `preDeployCommand` (a separate
"release job" step, matching ADR-034's original "migrations are a
release job, never application startup" design) does not reliably fire
when deploying via `railway up` — see docs/SPRINTS/sprint-033.md §1.2
for the investigation. The migration itself was never skipped or
silently ignored; it simply never ran, and nothing surfaced that.

This module is the fix: a small script that runs before `uvicorn` ever
binds its port, invoked directly by the Dockerfile's `CMD` — not by
FastAPI's ASGI lifespan (`app/core/startup.py` still never touches
Alembic; that separation from ADR-034 is preserved). It runs in every
container's own startup, guarded by a Postgres advisory lock so it
stays safe if production is ever scaled beyond one replica (the
concurrent-replica race ADR-034 explicitly calls out): only the
container that acquires the lock actually runs `alembic upgrade head`;
any others block briefly, then find the database already at head
(upgrade is idempotent) once they acquire it.

Fails closed: a non-zero exit here means the Dockerfile's `CMD` never
execs into `uvicorn`, so the container never binds its health-check
port, Railway's rollout never promotes it to serve traffic, and the
previous revision keeps serving — migration failure is observable
(plain stdout/stderr, captured in Railway's normal deploy logs) and
blocks unsafe promotion, exactly as ADR-034 requires.

`deploy/railway/api.railway.toml`'s `preDeployCommand` is left in place
as a harmless, idempotent redundant safety net — running `alembic
upgrade head` twice is a no-op the second time.
"""

import subprocess
import sys

from sqlalchemy import create_engine, text

from app.core.config import settings

# Arbitrary but stable — must be unique to this application's migration
# gate so it never collides with an unrelated advisory lock elsewhere.
_ADVISORY_LOCK_KEY = 785_032_033


def run_runtime_check() -> int:
    return subprocess.run([sys.executable, "-m", "app.core.runtime_check"]).returncode


def run_migration_under_lock() -> int:
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})
            try:
                upgrade = subprocess.run(["alembic", "upgrade", "head"])
                if upgrade.returncode != 0:
                    return upgrade.returncode
                subprocess.run(["alembic", "current"])
                return 0
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
    finally:
        engine.dispose()


def main() -> int:
    check_code = run_runtime_check()
    if check_code != 0:
        print("Migration gate: runtime configuration check failed — aborting startup.", file=sys.stderr)
        return check_code

    migration_code = run_migration_under_lock()
    if migration_code != 0:
        print("Migration gate: alembic upgrade head failed — aborting startup.", file=sys.stderr)
        return migration_code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
