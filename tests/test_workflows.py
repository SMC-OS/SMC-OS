"""GeoCore Premium OS Plan 01 — the trade-adaptive workflow engine.

Grows task-by-task alongside app/workflows/*: Task 2 covers the system
workflow template library in isolation (no DB); later tasks add
persistence, transition, gate and consumer-integration coverage.
"""

from app.trades.catalogue import TRADE_KEYS
from app.workflows.catalogue import SYSTEM_WORKFLOWS, template_for_trade
from app.workflows.models import WorkflowRole


# ---------------------------------------------------------------------------
# Task 2 — system workflow template library
# ---------------------------------------------------------------------------


def test_every_trade_has_a_system_workflow():
    for trade_key in TRADE_KEYS:
        template = template_for_trade(trade_key)
        assert template is not None
        if trade_key == "other":
            assert template.key == "general_v1"
        else:
            assert template.key == f"{trade_key}_v1"


def test_specific_template_keys():
    assert template_for_trade("electrical").key == "electrical_v1"
    assert template_for_trade("plumbing").key == "plumbing_v1"
    assert template_for_trade("stone").key == "stone_v1"
    assert template_for_trade("other").key == "general_v1"


def test_unknown_or_absent_trade_falls_back_to_general():
    assert template_for_trade(None).key == "general_v1"
    assert template_for_trade("not-a-real-trade").key == "general_v1"


def test_electrical_workflow_has_testing_and_certification():
    labels = [stage.label for stage in SYSTEM_WORKFLOWS["electrical_v1"].stages]
    assert "First Fix" in labels
    assert "Second Fix" in labels
    assert "Testing" in labels
    assert "Certification" in labels


def test_stone_workflow_has_specialist_stages():
    labels = [stage.label for stage in SYSTEM_WORKFLOWS["stone_v1"].stages]
    assert "Template" in labels
    assert "Fabrication" in labels
    assert "QC" in labels
    assert "Installation" in labels


def test_every_non_side_stage_has_semantic_role():
    for template in SYSTEM_WORKFLOWS.values():
        for stage in template.stages:
            assert isinstance(stage.role, WorkflowRole)


def test_every_template_ends_terminal_at_complete():
    for template in SYSTEM_WORKFLOWS.values():
        last = template.stages[-1]
        assert last.terminal is True
        assert last.role == WorkflowRole.COMPLETED
        assert last.label == "Complete"


def test_every_template_starts_at_enquiry_lead():
    for template in SYSTEM_WORKFLOWS.values():
        first = template.stages[0]
        assert first.label == "Enquiry"
        assert first.role == WorkflowRole.LEAD


def test_stage_keys_are_unique_within_a_template_and_positions_are_sequential():
    for template in SYSTEM_WORKFLOWS.values():
        keys = [stage.key for stage in template.stages]
        assert len(keys) == len(set(keys)), template.key
        positions = [stage.position for stage in template.stages]
        assert positions == list(range(len(positions))), template.key


def test_all_28_trades_produce_distinct_templates_except_other():
    # "other" intentionally shares general_v1 with the unknown-trade
    # fallback; every other trade gets its own template.
    keys_seen = {}
    for trade_key in TRADE_KEYS:
        template = template_for_trade(trade_key)
        keys_seen.setdefault(template.key, set()).add(trade_key)
    assert keys_seen["general_v1"] == {"other"}
