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

Sprint 038, Phase 3: also retries pending failed communications
(app.communications.service.DeliveryService.retry_pending) after the
scan. Folded into this existing cron entrypoint rather than a new
scheduled Railway service — the brief's own "do not introduce
unnecessary infrastructure if the existing job architecture can handle
the initial scale safely" (§11), and this job already runs on a schedule
against every tenant, exactly what a retry sweep also needs. `--now` has
no effect on the retry step: a retry itself has no notion of "as of a
given time" the way the scan's lookahead windows do.
"""

import argparse
import json
import sys
from datetime import datetime, timezone

from app.automations.scan import automation_scanner
from app.communications.service import delivery_service
from app.database.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate time-based (scan) automation triggers and retry pending email sends."
    )
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="ISO 8601 timestamp to evaluate the scan against, instead of the real current "
        "time (verification only). Does not affect the retry step.",
    )
    args = parser.parse_args(argv)

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)

    try:
        with SessionLocal() as db:
            scan_result = automation_scanner.run(db, now=now)
            retry_result = delivery_service.retry_pending(db)
    except Exception as exc:  # noqa: BLE001 — top-level job boundary, must never crash silently
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps({"scan": scan_result.as_dict(), "communications_retry": retry_result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
