"""Pure-logic tests for the A1 operator tools (approval gate and preflight evaluators).

These always run: no database, Railway or filesystem privileges are needed. The synthetic
pgBackRest JSON below follows the documented `pgbackrest info --output=json` shape and is a
PARSER test only; it is not evidence about the real staging stanza.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "recovery"))

import approval  # noqa: E402
import operator_preflight as pf  # noqa: E402

NOW = datetime(2026, 11, 10, 10, 5, tzinfo=timezone.utc)
FMT = "%Y-%m-%dT%H:%M:%SZ"


def good(**override):
    data = {
        "schema": "geocore-a1-approval/1", "approved_by": "Owner", "approved_at_utc": "2026-11-08T12:00:00Z",
        "window_start": "2026-11-10T10:00:00Z", "window_end": "2026-11-10T10:30:00Z", "operator": "op",
        "users_notified_at_utc": "2026-11-09T09:00:00Z", "notification_channel": "email",
        "private_storage_description": "encrypted ext4", "private_storage_approved": True,
        "private_storage_encryption_attested": True, "barrier_operational_procedure_approved": True,
        "scope_staging_only": True, "historical_backups_untouched": True, "production_untouched": True,
    }
    data.update(override)
    return data


def write(tmp_path, data):
    p = tmp_path / "a.json"
    p.write_text(json.dumps(data))
    return p


def test_a_complete_approval_inside_its_window_is_accepted(tmp_path):
    assert approval.validate_approval(write(tmp_path, good()), now=NOW, operator="op")["operator"] == "op"


@pytest.mark.parametrize(
    "override,needle",
    [
        ({"users_notified_at_utc": "2026-11-10T08:00:00Z"}, "24 hours"),
        ({"window_end": "2026-11-10T10:45:00Z"}, "30 minutes"),
        ({"approved_at_utc": "2026-11-10T10:02:00Z"}, "before the window opens"),
        ({"private_storage_approved": False}, "private_storage_approved"),
        ({"private_storage_encryption_attested": False}, "private_storage_encryption_attested"),
        ({"barrier_operational_procedure_approved": False}, "barrier_operational_procedure_approved"),
        ({"scope_staging_only": False}, "scope_staging_only"),
        ({"production_untouched": False}, "production_untouched"),
        ({"operator": "someone-else"}, "operator differs"),
        ({"window_start": "10 Nov 10:00"}, "exact UTC"),
        ({"approved_by": ""}, "approved_by"),
        ({"schema": "x"}, "schema"),
    ],
)
def test_each_missing_or_wrong_item_blocks_the_gate(tmp_path, override, needle):
    with pytest.raises(approval.ApprovalError) as caught:
        approval.validate_approval(write(tmp_path, good(**override)), now=NOW, operator="op")
    assert needle in str(caught.value)


def test_window_must_be_open_and_match_the_requested_one(tmp_path):
    p = write(tmp_path, good())
    with pytest.raises(approval.ApprovalError, match="not open"):
        approval.validate_approval(p, now=NOW + timedelta(hours=1), operator="op")
    with pytest.raises(approval.ApprovalError, match="differs from the approved window"):
        approval.validate_approval(p, now=NOW, operator="op", window_start="2026-11-10T11:00:00Z")
    approval.validate_approval(p, now=NOW - timedelta(days=1), require_window_open=False)


def test_missing_file_or_template_is_unapproved():
    with pytest.raises(approval.ApprovalError, match="UNAPPROVED"):
        approval.validate_approval(None, now=NOW)
    template = Path(__file__).resolve().parents[1] / "artifacts/qa/stone-hard-2026-11-05/a1-owner-approval.TEMPLATE.json"
    with pytest.raises(approval.ApprovalError) as caught:
        approval.validate_approval(template, now=NOW)
    assert len(caught.value.problems) >= 8


MOUNTS = "overlay / overlay rw 0 0\n/dev/sdc /mnt/wsl ext4 rw 0 0\nC:\\134 /mnt/c 9p rw 0 0\n/dev/sdd /home/op ext4 rw 0 0\n"


def test_storage_path_classification():
    assert pf.filesystem_for(Path("/mnt/c/Users/x"), MOUNTS) == "9p"
    assert pf.filesystem_for(Path("/home/op/recovery"), MOUNTS) == "ext4"
    assert [s for s, _ in pf.check_storage_path(Path("/mnt/c/Users/x"), MOUNTS)].count("FAIL") == 2
    assert [s for s, _ in pf.check_storage_path(Path("/home/op/OneDrive/rec"), MOUNTS)] == ["FAIL"]
    assert pf.check_storage_path(Path("/home/op/recovery"), MOUNTS) == []


def test_wsl_and_version_parsing():
    assert pf.wsl_kind("Linux version 5.15.153.1-microsoft-standard-WSL2") == "wsl2"
    assert pf.wsl_kind("Linux version 4.4.0-19041-Microsoft") == "wsl1"
    assert pf.wsl_kind("Linux version 6.8.0-generic") == "not-wsl"
    assert pf.parse_major("18.6") == 18 and pf.parse_major("16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)") == 16


def test_transfer_estimate_uses_the_budget():
    assert pf.estimate_transfer(50_000_000, 10, 275_645_492, 480)["status"] == "PASS"       # ~55 s
    assert pf.estimate_transfer(7_650_000, 10, 275_645_492, 480)["status"] == "WARN"        # ~360 s: over half the budget
    assert pf.estimate_transfer(5_000_000, 10, 275_645_492, 480)["status"] == "FAIL"        # ~551 s: over the budget
    assert pf.estimate_transfer(1_000_000, 10, 275_645_492, 480)["status"] == "FAIL"
    assert pf.estimate_transfer(0, 10, 1, 480)["status"] == "FAIL"


def arch(**kw):
    base = {"last_archived_wal": "000000010000000000000A5", "last_archived_time": NOW - timedelta(minutes=2), "failed_count": 0,
            "last_failed_wal": None, "last_failed_time": None}
    base.update(kw)
    return base


def test_archiver_decision_rule():
    ok = pf.evaluate_archiver(arch(), now=NOW, max_lag_s=7200, failures_explained=None)
    assert ok["status"] == "PASS"
    hist = arch(failed_count=2, last_failed_wal="000000010000000000000A1", last_failed_time=NOW - timedelta(days=4))
    assert pf.evaluate_archiver(hist, now=NOW, max_lag_s=7200, failures_explained=None)["status"] == "WARN"
    assert pf.evaluate_archiver(hist, now=NOW, max_lag_s=7200, failures_explained="pgbackrest log line 12")["status"] == "PASS"
    stuck = arch(failed_count=1, last_failed_wal="000000010000000000000A9", last_failed_time=NOW)
    assert pf.evaluate_archiver(stuck, now=NOW, max_lag_s=7200, failures_explained="x")["status"] == "FAIL"
    lagging = arch(last_archived_time=NOW - timedelta(hours=17))
    assert pf.evaluate_archiver(lagging, now=NOW, max_lag_s=7200, failures_explained=None)["status"] == "FAIL"
    assert pf.evaluate_archiver(arch(last_archived_wal=None, last_archived_time=None), now=NOW, max_lag_s=1, failures_explained=None)["status"] == "FAIL"


def stanza(**kw):
    s = {"name": "main", "status": {"code": 0, "message": "ok"},
         "backup": [{"label": "20261105-070000F", "type": "full", "error": False, "timestamp": {"start": 1, "stop": 2},
                     "archive": {"start": "0000000100000000000000A2", "stop": "0000000100000000000000A3"}}],
         "archive": [{"id": "18-1", "min": "0000000100000000000000A0", "max": "0000000100000000000000B0"}]}
    s.update(kw)
    return [s]


def test_pgbackrest_continuity_parser_on_synthetic_json():
    assert pf.evaluate_pgbackrest(stanza())["status"] == "PASS"
    gap = stanza(archive=[{"id": "18-1", "min": "0000000100000000000000A4", "max": "0000000100000000000000B0"}])
    assert pf.evaluate_pgbackrest(gap)["status"] == "FAIL"
    assert pf.evaluate_pgbackrest(stanza(status={"code": 2, "message": "missing stanza"}))["status"] == "FAIL"
    assert pf.evaluate_pgbackrest(stanza(backup=[]))["status"] == "FAIL"
    assert pf.evaluate_pgbackrest(stanza(), archiver_last_wal="0000000100000000000000C0")["status"] == "WARN"
