"""Sprint 024 (docs/SPRINTS/sprint-024.md) — the operational entrypoint for
the stale-enquiry follow-up automation. Thin: all business logic lives in
app.notifications.follow_up_service, fully unit-tested independently of
this script. No HTTP boundary, no role/auth dependency (§7/§9/§11) — run
directly via `python -m app.jobs.follow_up`, e.g. through `railway ssh`
against staging, exactly like `alembic` commands already are.

--now is an explicit escape hatch for verification only (staging/E2E
runs that can't wait 7 real days for a Project to go stale) — production
operation always uses the real current time.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from app.database.database import SessionLocal
from app.notifications.follow_up_service import follow_up_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the stale-enquiry follow-up automation.")
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="ISO 8601 timestamp to evaluate against, instead of the real current time "
        "(verification only).",
    )
    args = parser.parse_args(argv)

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)

    try:
        with SessionLocal() as db:
            result = follow_up_service.run(db, now=now)
    except Exception as exc:  # noqa: BLE001 — top-level job boundary, must never crash silently
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "examined": result.examined,
                "created": result.created,
                "skipped_existing": result.skipped_existing,
                "skipped_not_due": result.skipped_not_due,
                "skipped_no_recipient": result.skipped_no_recipient,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
