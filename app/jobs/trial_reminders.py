"""Phase B — operational entrypoint for the no-card trial reminder emails.

Same thin-CLI shape as app/jobs/follow_up.py: all logic lives in
app.billing.trial_reminders, unit-tested on its own. Idempotent, so it is
safe on any schedule, and a no-op wherever email is not configured.
app/jobs/follow_up.py also calls it, so whichever scheduler runs the
follow-up job runs this too (see PRODUCTION_RUNBOOK §14 for the current
state of that scheduler).

    python -m app.jobs.trial_reminders
    python -m app.jobs.trial_reminders --now 2026-10-07T09:00:00+00:00   # verification only
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from app.billing.trial_reminders import trial_reminder_service
from app.database.database import SessionLocal


def run(now: datetime) -> dict:
    with SessionLocal() as db:
        return asdict(trial_reminder_service.run(db, now=now))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send no-card trial reminder emails.")
    parser.add_argument("--now", type=str, default=None, help="ISO 8601 time to evaluate at (verification only).")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    try:
        result = run(now)
    except Exception as exc:  # noqa: BLE001 — top-level job boundary
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
