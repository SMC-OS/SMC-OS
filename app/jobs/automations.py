"""Sprint 036 (Workstream G) — the operational entrypoint for
scan-evaluated automation triggers (quote approaching expiry, project
approaching start date).

Thin by design, exactly like app/jobs/follow_up.py: all logic lives in
app.automations.scan, fully unit-testable independently of this script.
No HTTP boundary and no auth dependency — run directly via
`python -m app.jobs.automations`, e.g. through `railway ssh` against
staging, the same way alembic and the follow-up job already are.

--now is an explicit escape hatch for verification only (a staging or E2E
run that cannot wait three real days for a quote to approach expiry).
Production operation always uses the real current time.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from app.automations.scan import automation_scanner
from app.database.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate time-based (scan) automation triggers."
    )
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="ISO 8601 timestamp to evaluate against, instead of the real current "
        "time (verification only).",
    )
    args = parser.parse_args(argv)

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)

    try:
        with SessionLocal() as db:
            result = automation_scanner.run(db, now=now)
    except Exception as exc:  # noqa: BLE001 — top-level job boundary, must never crash silently
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result.as_dict()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
