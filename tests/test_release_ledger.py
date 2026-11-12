"""The release ledger must be valid and must refuse to over-claim."""

import copy
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("ledger", Path(__file__).resolve().parents[1] / "scripts/qa/release_ledger.py")
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)
DOC = json.loads(ledger.DATA.read_text(encoding="utf-8"))


def gate(**kw):
    base = {"id": "X", "purpose": "p", "verified_in": ["isolated_qa"], "sha": "s", "evidence": [], "status": "UNKNOWN",
            "owner": "o", "remaining": "r", "blocks_initial_release": True}
    base.update(kw)
    return {"gates": [base]}


def test_the_committed_ledger_is_valid():
    assert ledger.validate(DOC) == []


def test_no_gate_is_verified_without_evidence_in_its_own_environment():
    assert ledger.validate(gate(status="VERIFIED")) != []
    local_only = gate(status="VERIFIED", evidence=[{"env": "local", "what": "unit tests"}])
    assert any("VERIFIED without evidence" in e for e in ledger.validate(local_only))  # local never satisfies isolated_qa
    ok = gate(status="VERIFIED", evidence=[{"env": "isolated_qa", "what": "browser run"}])
    assert ledger.validate(ok) == []


def test_not_applicable_needs_a_reason_and_statuses_are_closed():
    assert ledger.validate(gate(status="NOT_APPLICABLE")) != []
    assert ledger.validate(gate(status="PASS")) != []


def test_the_release_is_not_claimed_ready_while_launch_gates_are_open():
    open_gates = [g for g in DOC["gates"] if g["blocks_initial_release"] and g["status"] not in ("VERIFIED", "NOT_APPLICABLE")]
    assert open_gates, "if this ever fails, the verdict in the ledger must be revisited deliberately"
    assert DOC["verdict"] == "HARD NO-GO"


def test_render_lists_every_gate():
    text = ledger.render(copy.deepcopy(DOC))
    assert all(g["id"] in text for g in DOC["gates"])
