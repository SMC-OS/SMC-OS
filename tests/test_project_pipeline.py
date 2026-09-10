"""Trade-neutral project pipeline — Sprint 039, Workstream D.

These tests cover the *pure* pipeline domain: the stage-role vocabulary,
the named templates, and the transition graph. Nothing here touches the
database — resolving a tenant's configured pipeline is covered separately
in tests/test_project_pipeline_config.py.

The contract under test (docs/SPRINTS/sprint-039.md §3 D, §4 Decision 5):

  * The trade-neutral vocabulary is a set of semantic *roles*, not stage
    keys. Every consumer reasons about roles, so a stone tenant whose
    stage is called "fabricated" and a roofing tenant whose stage is
    called "in_progress" are both simply `in_progress` to the dashboard.
  * Stone/worktop stays fully supported, as a template rather than as
    GeoCore's core identity.
  * Transitions are graph-based, not a strict linear walk: forward one
    active stage, plus hold/resume and cancel.
"""

import pytest

from app.projects import pipeline


def test_the_trade_neutral_role_vocabulary_is_the_brief_s_pipeline():
    assert pipeline.ACTIVE_ROLE_ORDER == (
        "lead",
        "quoted",
        "approved",
        "scheduled",
        "in_progress",
        "completed",
    )
    assert set(pipeline.SIDE_ROLES) == {"on_hold", "cancelled"}
    assert set(pipeline.TERMINAL_ROLES) == {"completed", "cancelled"}


def test_the_standard_template_is_trade_neutral_and_keys_stages_by_role():
    """A new tenant's stage keys ARE the role names — there is no
    stone vocabulary anywhere in GeoCore's default pipeline."""
    stages = pipeline.template("standard")

    assert [stage.key for stage in stages] == [
        "lead",
        "quoted",
        "approved",
        "scheduled",
        "in_progress",
        "completed",
        "on_hold",
        "cancelled",
    ]
    assert all(stage.key == stage.role for stage in stages)


def test_the_stone_template_preserves_every_legacy_stage_key():
    """Sprint 006's pipeline survives verbatim as a specialist template —
    which is what lets Sprint 039's migration rewrite zero project rows
    (§4 Decision 2)."""
    stages = pipeline.template("stone")
    keys = [stage.key for stage in stages]

    assert keys[:7] == [
        "enquiry",
        "quoted",
        "booked",
        "templated",
        "fabricated",
        "installed",
        "complete",
    ]
    assert keys[7:] == ["on_hold", "cancelled"]


def test_the_stone_template_maps_its_stone_stages_onto_neutral_roles():
    roles = {stage.key: stage.role for stage in pipeline.template("stone")}

    assert roles["enquiry"] == "lead"
    assert roles["booked"] == "approved"
    # Three distinct stone stages, one shared neutral meaning: work is
    # under way. This is exactly what makes the dashboard trade-neutral
    # without touching a single project row.
    assert roles["templated"] == "in_progress"
    assert roles["fabricated"] == "in_progress"
    assert roles["installed"] == "in_progress"
    assert roles["complete"] == "completed"


def test_every_template_stage_declares_a_known_role_and_a_label():
    for name in pipeline.TEMPLATE_KEYS:
        for stage in pipeline.template(name):
            assert stage.role in pipeline.ROLES, (name, stage.key, stage.role)
            assert stage.label.strip(), (name, stage.key)


def test_an_unknown_template_name_raises_rather_than_silently_defaulting():
    with pytest.raises(KeyError):
        pipeline.template("plumbing-deluxe")


# --- The transition graph -------------------------------------------------


def _standard() -> pipeline.Pipeline:
    return pipeline.Pipeline(pipeline.template("standard"))


def _stone() -> pipeline.Pipeline:
    return pipeline.Pipeline(pipeline.template("stone"))


def test_forward_progress_is_still_exactly_one_stage_at_a_time():
    """Sprint 023's no-skip invariant is preserved for ordinary forward
    movement — only the next active stage is offered."""
    allowed = _standard().allowed_transitions("lead")

    assert "quoted" in allowed
    assert "approved" not in allowed
    assert "completed" not in allowed


def test_forward_progress_follows_the_tenant_s_own_stage_order():
    """The stone pipeline advances through its own three work stages, not
    through the standard template's."""
    stone = _stone()

    assert "templated" in stone.allowed_transitions("booked")
    assert "fabricated" in stone.allowed_transitions("templated")
    assert "installed" in stone.allowed_transitions("fabricated")
    assert "complete" in stone.allowed_transitions("installed")


def test_a_job_can_be_put_on_hold_from_any_active_stage():
    standard = _standard()

    for key in ("lead", "quoted", "approved", "scheduled", "in_progress"):
        assert "on_hold" in standard.allowed_transitions(key), key


def test_a_job_can_be_cancelled_from_any_non_terminal_stage():
    standard = _standard()

    for key in ("lead", "quoted", "approved", "scheduled", "in_progress", "on_hold"):
        assert "cancelled" in standard.allowed_transitions(key), key


def test_resuming_from_hold_may_return_to_any_active_stage_still_in_play():
    """A held job resumes where the business says it resumes — GeoCore has
    no basis for guessing, and constraining it adds no safety."""
    allowed = _standard().allowed_transitions("on_hold")

    assert {"lead", "quoted", "approved", "scheduled", "in_progress"} <= set(allowed)


def test_resuming_from_hold_can_never_jump_straight_to_completed():
    """Hold/resume is an escape hatch for stage order, never a way to
    fabricate a finished job — completion is always its own deliberate
    forward step."""
    assert "completed" not in _standard().allowed_transitions("on_hold")
    assert "complete" not in _stone().allowed_transitions("on_hold")


def test_a_terminal_stage_has_no_transitions_at_all():
    standard = _standard()

    assert standard.allowed_transitions("completed") == ()
    assert standard.allowed_transitions("cancelled") == ()


def test_an_unknown_stage_key_offers_no_transitions_rather_than_raising():
    """A project sitting on a stage its tenant has since removed must not
    crash the status endpoint — it simply has nowhere valid to go, and
    the service turns that into a refused transition."""
    assert _standard().allowed_transitions("fabricated") == ()


def test_the_initial_stage_is_the_first_lead_stage():
    assert _standard().initial_stage().key == "lead"
    assert _stone().initial_stage().key == "enquiry"


def test_a_stage_can_be_found_by_role_for_cross_module_callers():
    """Quote handoff creates a project at whatever this tenant calls
    "approved" — app/quotes/service.py must never name a stage key."""
    assert _standard().stage_for_role("approved").key == "approved"
    assert _stone().stage_for_role("approved").key == "booked"
    assert _stone().stage_for_role("lead").key == "enquiry"


def test_stage_for_role_returns_the_earliest_stage_carrying_that_role():
    """Stone has three in_progress stages; work starts at the first."""
    assert _stone().stage_for_role("in_progress").key == "templated"


def test_role_lookup_answers_for_a_known_stage_and_declines_an_unknown_one():
    stone = _stone()

    assert stone.role_of("fabricated") == "in_progress"
    assert stone.role_of("lead") is None
