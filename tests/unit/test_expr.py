import pytest

from justice_sim.util import expr as expr_util


@pytest.mark.unit
def test_predicate_supports_flags_statuses_counters_and_booleans():
    ctx = expr_util.build_predicate_context(
        case_index=1,
        coins=5,
        pop=0,
        mh=2,
        dismissals=0,
        retirement_chests=0,
        flags={"ghost_first_interaction_accepted"},
        statuses={"cannot_approve"},
        counters={"timmy_rejects": 3},
    )
    assert expr_util.evaluate_predicate(
        "flags.ghost_first_interaction_accepted == true", ctx
    )
    assert expr_util.evaluate_predicate("statuses.cannot_approve == true", ctx)
    assert expr_util.evaluate_predicate("counters.timmy_rejects >= 3", ctx)
    assert expr_util.evaluate_predicate(
        "has_flag('ghost_first_interaction_accepted')", ctx
    )
    assert not expr_util.evaluate_predicate("has_status('missing')", ctx)


@pytest.mark.unit
def test_predicate_missing_counter_defaults_to_zero():
    ctx = expr_util.build_predicate_context(
        case_index=1,
        coins=0,
        pop=0,
        mh=1,
        dismissals=0,
        retirement_chests=0,
        flags=set(),
        statuses=set(),
        counters={},
    )
    assert expr_util.evaluate_predicate("counters.unknown == 0", ctx)
    assert not expr_util.evaluate_predicate("counters.unknown > 0", ctx)


@pytest.mark.unit
def test_validate_predicate_rejects_unknown_name():
    error = expr_util.validate_predicate("unknown_var == 1")
    assert error is not None
