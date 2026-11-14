"""The ledger generator must never promote a status without staging evidence
on the release SHA, and must refuse evidence that does not exist."""

import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "build_qa_matrix", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "qa" / "build_qa_matrix.py"
)
matrix = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(matrix)


def test_local_evidence_never_changes_a_status():
    status, reason, _ = matrix.decide("Unknown", [{"environment": "local", "release_sha": "abc", "result": "pass"}], "abc")
    assert status == "Unknown"
    assert "not target-environment proof" in reason


def test_staging_evidence_on_another_sha_does_not_count():
    status, _, _ = matrix.decide("Unknown", [{"environment": "staging", "release_sha": "old", "result": "pass"}], "new")
    assert status == "Unknown"


def test_staging_pass_on_the_release_sha_verifies_and_a_failure_marks_defective():
    ok = {"environment": "staging", "release_sha": "abc", "result": "pass", "ref": "x"}
    bad = {**ok, "result": "fail"}
    assert matrix.decide("Unknown", [ok], "abc")[0] == "Verified"
    assert matrix.decide("Unknown", [ok, bad], "abc")[0] == "Defective"


def test_missing_evidence_file_aborts(tmp_path):
    index = tmp_path / "evidence.json"
    index.write_text('[{"item": "x", "ref": "does/not/exist.txt"}]', encoding="utf-8")
    with pytest.raises(SystemExit):
        matrix.load_evidence(index, tmp_path)


def test_notes_are_escaped():
    assert matrix.clean('<script>alert(1)</script>\nx') == "&lt;script&gt;alert(1)&lt;/script&gt; x"
