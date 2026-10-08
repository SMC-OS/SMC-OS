"""Operator-only staging smoke fixture: mark the synthetic smoke users verified.

`scripts/staging/smoke.py` signs up two fresh synthetic workspaces and then
drives the real authenticated API. Since Sprint 039 every workspace route
sits behind `require_billing_access` -> `require_verified_email`, so a fresh
signup is (correctly) refused until its email is verified. A smoke run has
no inbox, so it needs the same "already verified" fixture the E2E suite uses
(apps/web/e2e/verify-helper.ts) — but staging's database is private-network
only, so the write has to happen next to the database.

This is a CLI, never a route: there is no HTTP surface here, nothing imports
it from a router, and `python -m app.core.staging_fixture` can only be run by
someone with shell access to the container (`railway ssh`). It fails closed:

- refuses unless Railway reports this container's environment as exactly
  "staging" (production, unset and anything else are refused);
- takes a smoke run prefix, never an email or user id, and derives the only
  two addresses it will ever touch (`<prefix>-a|b@example.invalid`);
- only touches a user whose tenant is named exactly `<prefix>-a|b` (the name
  smoke.py gave it at signup), that is still unverified and was created
  within the last hour;
- changes `email_verified_at` and nothing else — the no-card trial the
  signup created is left exactly as it was;
- prints counts only: no tokens, passwords, emails or user ids.
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

STAGING_ENVIRONMENT_NAME = "staging"
RUN_PREFIX_PATTERN = re.compile(r"^s019-[0-9a-f]{12}$")
SYNTHETIC_TENANTS = ("a", "b")
SYNTHETIC_EMAIL_DOMAIN = "example.invalid"
MAX_FIXTURE_AGE = timedelta(hours=1)


class FixtureRefused(Exception):
    """The fixture will not run. The message is safe to print."""


def assert_staging(environ: Mapping[str, str] | None = None) -> None:
    environment = (os.environ if environ is None else environ).get("RAILWAY_ENVIRONMENT_NAME")
    if environment != STAGING_ENVIRONMENT_NAME:
        raise FixtureRefused("refused: this fixture only runs in the Railway staging environment")


def synthetic_email(run_prefix: str, tenant: str) -> str:
    return f"{run_prefix}-{tenant}@{SYNTHETIC_EMAIL_DOMAIN}"


def verify_synthetic_users(
    db: Session,
    run_prefix: str,
    tenants: tuple[str, ...] = SYNTHETIC_TENANTS,
    *,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> int:
    """Marks the smoke run's own users verified. Returns how many changed."""
    from app.database import crud

    assert_staging(environ)
    if not RUN_PREFIX_PATTERN.fullmatch(run_prefix):
        raise FixtureRefused("refused: run prefix is not a smoke run prefix")
    if not tenants or any(tenant not in SYNTHETIC_TENANTS for tenant in tenants):
        raise FixtureRefused("refused: unknown synthetic tenant")

    now = now or datetime.now(timezone.utc)
    users = []
    for tenant in tenants:
        user = crud.get_user_by_email(db, synthetic_email(run_prefix, tenant))
        tenant_row = crud.get_tenant_by_id(db, user.tenant_id) if user is not None else None
        if user is None or tenant_row is None or tenant_row.name != f"{run_prefix}-{tenant}":
            raise FixtureRefused("refused: no synthetic user created by this smoke run")
        if now - user.created_at > MAX_FIXTURE_AGE:
            raise FixtureRefused("refused: synthetic user is older than this smoke run")
        users.append(user)

    changed = 0
    for user in users:
        if user.email_verified_at is None:
            user.email_verified_at = now
            changed += 1
    db.commit()
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operator-only staging smoke fixture.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-email", help="Mark a smoke run's synthetic users verified.")
    verify.add_argument("--run-prefix", required=True)
    args = parser.parse_args(argv)

    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        changed = verify_synthetic_users(db, args.run_prefix)
    except FixtureRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        db.close()
    print(json.dumps({"verified": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
