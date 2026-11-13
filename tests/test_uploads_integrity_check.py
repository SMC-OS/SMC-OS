import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("uic", Path(__file__).resolve().parents[1] / "scripts/qa/uploads_integrity_check.py")
uic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uic)
NOW = 10_000.0


def test_consistent_state_reports_nothing():
    assert uic.compare({"a.pdf": 5}, {"a.pdf": (5, 0.0)}, now=NOW, min_age_s=600) == {"orphan_files": [], "missing_files": [], "size_mismatches": []}


def test_orphan_missing_and_size_mismatch_are_each_reported():
    out = uic.compare({"row-only.pdf": 1, "wrong.pdf": 5}, {"file-only.pdf": (3, 0.0), "wrong.pdf": (9, 0.0)}, now=NOW, min_age_s=600)
    assert out == {"orphan_files": ["file-only.pdf"], "missing_files": ["row-only.pdf"], "size_mismatches": ["wrong.pdf"]}


def test_an_upload_in_progress_and_the_startup_probe_are_not_orphans():
    files = {"just-written.pdf": (3, NOW - 5), ".simo-os-write-probe-abc": (0, 0.0)}
    assert uic.compare({}, files, now=NOW, min_age_s=600)["orphan_files"] == []
