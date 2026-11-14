"""Owner approval gate for any STAGING mutation in A1 (barrier engage and capture).

The approval file is written and signed off by the OWNER, never by an agent.  Nothing in
the repository contains a filled-in copy; `artifacts/qa/.../a1-owner-approval.TEMPLATE.json`
is deliberately all-null, i.e. UNAPPROVED.

A staging mutation is refused unless every item is present, the time window is exactly the
one approved (and now open, at most 30 minutes), users were told at least 24 hours before
the window opens, the operator matches, private storage and the barrier procedure were
approved, and the scope is staging-only.  Standard library only.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "geocore-a1-approval/1"
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MIN_NOTICE = timedelta(hours=24)
MAX_WINDOW = timedelta(minutes=30)
REQUIRED_TEXT = ("approved_by", "operator", "private_storage_description", "notification_channel")
REQUIRED_TRUE = (
    "private_storage_approved",
    "private_storage_encryption_attested",
    "barrier_operational_procedure_approved",
    "scope_staging_only",
    "historical_backups_untouched",
    "production_untouched",
)


class ApprovalError(RuntimeError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _time(value: Any, field: str, problems: list[str]) -> datetime | None:
    if not isinstance(value, str):
        problems.append(f"{field} is missing")
        return None
    try:
        return datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        problems.append(f"{field} must be an exact UTC time like 2026-11-10T10:00:00Z")
        return None


def validate_approval(
    path: Path | None,
    *,
    now: datetime,
    operator: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    require_window_open: bool = True,
) -> dict[str, Any]:
    if path is None:
        raise ApprovalError(["no owner approval file was supplied (--approval-file); staging is UNAPPROVED"])
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ApprovalError(["the approval file cannot be read as JSON"]) from None
    problems: list[str] = []
    if data.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    for field in REQUIRED_TEXT:
        if not isinstance(data.get(field), str) or not data[field].strip():
            problems.append(f"{field} is missing")
    for field in REQUIRED_TRUE:
        if data.get(field) is not True:
            problems.append(f"{field} must be true")
    start = _time(data.get("window_start"), "window_start", problems)
    end = _time(data.get("window_end"), "window_end", problems)
    approved = _time(data.get("approved_at_utc"), "approved_at_utc", problems)
    notified = _time(data.get("users_notified_at_utc"), "users_notified_at_utc", problems)
    if start and end:
        if end <= start or end - start > MAX_WINDOW:
            problems.append("the window must be positive and at most 30 minutes")
        if require_window_open and not (start <= now < end):
            problems.append("the approved window is not open now")
        if approved and approved >= start:
            problems.append("approval must be recorded before the window opens")
        if notified and start - notified < MIN_NOTICE:
            problems.append("users must be notified at least 24 hours before the window opens")
        if notified and approved and notified > now:
            problems.append("users_notified_at_utc is in the future")
        if window_start and window_start != data.get("window_start"):
            problems.append("the window start differs from the approved window")
        if window_end and window_end != data.get("window_end"):
            problems.append("the window end differs from the approved window")
    if operator is not None and data.get("operator") != operator:
        problems.append("the operator differs from the approved operator")
    if problems:
        raise ApprovalError(problems)
    return data
