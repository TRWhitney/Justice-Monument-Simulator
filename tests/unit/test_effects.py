import pytest

from justice_sim.engine.effects import (
    advance_case,
    apply_effects,
    apply_outcome,
    resolve_expr,
    resolve_probability,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import BernoulliSpec, EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.util.validation import build_minimal_data


@pytest.mark.unit
def test_apply_add_set_clamp_effects():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=5, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(type="add_resource", params={"resource": "coins", "amount": 3}),
        EffectSpec(type="set_resource", params={"resource": "pop", "value": 2}),
        EffectSpec(type="clamp_resource", params={"resource": "coins", "max": 6}),
    ]
    new_state = apply_effects(state, effects, data)
    assert new_state.coins == 6
    assert new_state.pop == 2


@pytest.mark.unit
def test_main_resources_round_scaled_values_to_nearest_whole_numbers():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=1, pop=1, mh=1, dismissals=1, retirement_chests=1
    )
    effects = [
        EffectSpec(type="add_resource", params={"resource": "coins", "amount": 0.2}),
        EffectSpec(type="set_resource", params={"resource": "pop", "value": 1.2}),
        EffectSpec(type="multiply_resource", params={"resource": "mh", "factor": 1.2}),
        EffectSpec(
            type="set_resource",
            params={"resource": "retirement_chests", "value": 1.2},
        ),
        EffectSpec(
            type="add_resource", params={"resource": "dismissals", "amount": -0.2}
        ),
    ]
    new_state = apply_effects(state, effects, data)
    assert new_state.coins == 1
    assert new_state.pop == 1
    assert new_state.mh == 1
    assert new_state.retirement_chests == 1
    assert new_state.dismissals == 1


@pytest.mark.unit
def test_main_resource_losses_round_to_nearest_whole_number():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=10, pop=10, mh=3, dismissals=0, retirement_chests=0
    )

    new_state = apply_effects(
        state,
        [
            EffectSpec(
                type="add_resource",
                params={"resource": "coins", "amount": -2.6},
            ),
            EffectSpec(
                type="add_resource",
                params={"resource": "pop", "amount": -3.9},
            ),
        ],
        data,
    )

    assert new_state.coins == 7
    assert new_state.pop == 6


@pytest.mark.unit
def test_zero_probability_bernoulli_uses_else_branch_at_zero_roll():
    class ZeroRng:
        @staticmethod
        def random():
            return 0.0

    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    outcome = OutcomeSpec(
        random=BernoulliSpec(
            type="bernoulli",
            p=0.0,
            then_effects=(
                EffectSpec(
                    type="add_resource",
                    params={"resource": "coins", "amount": 10},
                ),
            ),
            else_effects=(),
        )
    )

    new_state, label = apply_outcome(state, outcome, data, ZeroRng())

    assert new_state.coins == 0
    assert label == "else"


@pytest.mark.unit
def test_status_duration_decrements_each_case():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(
            type="add_status",
            params={"status": "cannot_approve"},
            duration_cases=2,
        )
    ]
    state_with_status = apply_effects(state, effects, data)
    assert "cannot_approve" in state_with_status.statuses
    assert state_with_status.statuses["cannot_approve"].remaining_cases == 2

    state_after_one = advance_case(state_with_status, data)
    assert state_after_one.statuses["cannot_approve"].remaining_cases == 1

    state_after_two = advance_case(state_after_one, data)
    assert "cannot_approve" not in state_after_two.statuses


@pytest.mark.unit
def test_status_duration_can_start_next_case():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(
            type="add_status",
            params={"status": "cannot_approve", "data": {"starts_next_case": True}},
            duration_cases=2,
        )
    ]
    state_with_status = apply_effects(state, effects, data)
    assert state_with_status.statuses["cannot_approve"].remaining_cases == 2

    state_after_one = advance_case(state_with_status, data)
    assert state_after_one.statuses["cannot_approve"].remaining_cases == 2

    state_after_two = advance_case(state_after_one, data)
    assert state_after_two.statuses["cannot_approve"].remaining_cases == 1

    state_after_three = advance_case(state_after_two, data)
    assert "cannot_approve" not in state_after_three.statuses


@pytest.mark.unit
def test_scheduled_events_trigger_on_future_case():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(
            type="schedule_effects",
            params={
                "after_cases": 1,
                "effects": [
                    {
                        "type": "add_resource",
                        "params": {"resource": "coins", "amount": 2},
                    }
                ],
            },
        )
    ]
    state_with_event = apply_effects(state, effects, data)
    assert state_with_event.scheduled_events

    state_after = advance_case(state_with_event, data)
    assert state_after.case_index == 2
    assert state_after.coins == 2


@pytest.mark.unit
def test_random_range_resource_is_deterministic_with_seed():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(
            type="random_range_resource",
            params={"resource": "coins", "min": 1, "max": 3},
        )
    ]
    expected_rng = Rng(7)
    expected = expected_rng.randint(1, 3)
    new_state = apply_effects(state, effects, data, Rng(7))
    assert new_state.coins == expected


@pytest.mark.unit
def test_random_exchange_uses_same_amount_for_both_resources():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=10, pop=1, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(
            type="random_exchange",
            params={
                "take_resource": "coins",
                "give_resource": "pop",
                "min": 2,
                "max": 2,
            },
        )
    ]
    new_state = apply_effects(state, effects, data, Rng(1))
    assert new_state.coins == 8
    assert new_state.pop == 3


@pytest.mark.unit
def test_resolve_expr_and_probability_string_formats():
    data = build_minimal_data()
    state = GameState(
        case_index=6, coins=0, pop=20, mh=3, dismissals=0, retirement_chests=0
    )
    assert resolve_expr("case_scale + 1", state, data) == 3
    probability = resolve_probability(
        {"expr": "(40*pop)/(pop+20)", "format": "percent"}, state, data
    )
    assert probability == pytest.approx(0.2)
    probability_raw = resolve_probability("(40*pop)/(pop+20)", state, data)
    assert probability_raw == pytest.approx(20.0)


@pytest.mark.unit
def test_resolve_expr_scaling_modes():
    data = build_minimal_data()
    state = GameState(
        case_index=6, coins=0, pop=20, mh=3, dismissals=0, retirement_chests=0
    )
    assert resolve_expr({"expr": "2"}, state, data) == pytest.approx(2.0)
    assert resolve_expr({"expr": "2", "scaling": "none"}, state, data) == pytest.approx(
        2.0
    )
    assert resolve_expr({"expr": "2", "scaling": "case"}, state, data) == pytest.approx(
        4.0
    )
    assert resolve_expr(
        {"expr": "-1", "scaling": "harbinger"}, state, data
    ) == pytest.approx(-2.0)


@pytest.mark.unit
def test_flags_statuses_and_modifiers_apply():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(type="add_flag", params={"flag": "flag1"}),
        EffectSpec(type="add_status", params={"status": "locked"}, duration_cases=2),
        EffectSpec(
            type="modify_encounter_weights",
            params={"offer_weights": {"offer": 0.5}, "mode": "set"},
            duration_cases=2,
        ),
    ]
    new_state = apply_effects(state, effects, data)
    assert "flag1" in new_state.flags
    assert "locked" in new_state.statuses
    assert new_state.encounter_modifiers

    cleanup = [
        EffectSpec(type="remove_flag", params={"flag": "flag1"}),
        EffectSpec(type="remove_status", params={"status": "locked"}),
    ]
    cleaned = apply_effects(new_state, cleanup, data)
    assert "flag1" not in cleaned.flags
    assert "locked" not in cleaned.statuses


@pytest.mark.unit
def test_schedule_after_cases_and_end_run_effects():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effect = EffectSpec(
        type="add_resource",
        params={"resource": "coins", "amount": 2},
        schedule_after_cases=2,
    )
    scheduled = apply_effects(state, [effect], data)
    assert scheduled.scheduled_events[0].trigger_case_index == 3

    ended = apply_effects(
        state, [EffectSpec(type="end_run", params={"reason": "test"})], data
    )
    assert ended.ended


@pytest.mark.unit
def test_require_next_action_sets_penalty_effects():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(
            type="require_next_action",
            params={
                "action": "approve",
                "penalty_effects": [
                    {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
                ],
            },
        )
    ]
    new_state = apply_effects(state, effects, data)
    assert new_state.required_action == "approve"
    assert new_state.required_action_penalty_effects


@pytest.mark.unit
def test_scheduled_effect_snapshots_scaled_amount():
    data = build_minimal_data()
    state = GameState(
        case_index=6, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    effect = EffectSpec(
        type="add_resource",
        params={
            "resource": "coins",
            "amount": {"expr": "3", "scaling": "case", "snapshot": True},
        },
        schedule_after_cases=1,
    )
    scheduled = apply_effects(state, [effect], data)
    stored_amount = scheduled.scheduled_events[0].effects[0].params["amount"]
    assert stored_amount == 6


@pytest.mark.unit
def test_resource_floor_prevents_pop_below_min():
    data = build_minimal_data()
    state = GameState(
        case_index=1, coins=0, pop=6, mh=3, dismissals=0, retirement_chests=0
    )
    effects = [
        EffectSpec(type="set_resource_floor", params={"resource": "pop", "min": 5}),
        EffectSpec(type="add_resource", params={"resource": "pop", "amount": -10}),
    ]
    new_state = apply_effects(state, effects, data)
    assert new_state.pop == 5


@pytest.mark.unit
def test_probability_resources_skip_unread_numeric_context(data_factory, monkeypatch):
    from justice_sim.engine import effects

    data = data_factory()
    state = GameState(3, 100, 10, 5, 2, 0)
    expression = "(40*pop)/(pop+20)"

    def unnecessary(*args):
        pytest.fail(
            "A resource-only probability does not need unrelated scaling/context"
        )

    monkeypatch.setattr(effects, "_build_numeric_context", unnecessary)
    assert (
        effects.resolve_probability(
            {"expr": expression, "format": "percent"}, state, data
        )
        == ((40 * state.pop) / (state.pop + 20)) / 100
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "expression",
    [
        "(40*pop)/(pop+20)",
        "pop + 1",
        "min(pop, coins) + case_index / 2",
        "case_scale * pop",
        "counters.stage * pop",
        "(flags.ready and pop) or coins",
    ],
)
def test_probability_cache_matches_full_numeric_context(data_factory, expression):
    from dataclasses import replace
    from justice_sim.engine import effects
    from justice_sim.util import expr

    data = data_factory()
    data = replace(
        data,
        special_rules=replace(
            data.special_rules,
            case_scale=replace(data.special_rules.case_scale, expr="pop + case_index"),
        ),
    )
    for value in (10, 10.0, 2**53, float(2**53), 2**53 + 2):
        for coins in (3, 20):
            state = GameState(
                3,
                coins,
                value,
                5,
                2,
                0,
                counters={"stage": 2},
                flags=frozenset({"ready"}),
            )
            _, _, functions, variables = effects._build_numeric_context(state, data)
            expected = expr.evaluate_numeric(
                expression, expr.build_numeric_context(variables, functions)
            )
            assert (
                effects.resolve_probability(
                    {"expr": expression, "format": "unit"}, state, data
                )
                == expected
            )
            assert (
                effects.resolve_probability(
                    {"expr": expression, "format": "percent"}, state, data
                )
                == expected / 100
            )


@pytest.mark.unit
def test_probability_cache_preserves_negative_zero_and_errors(data_factory):
    import math
    from justice_sim.engine import effects
    from justice_sim.util.expr import ExprError

    data = data_factory()
    for pop in (0.0, -0.0, 0.0):
        state = GameState(2, 10, pop, 3, 2, 0)
        result = effects.resolve_probability(
            {"expr": "pop", "format": "unit"}, state, data
        )
        assert math.copysign(1, result) == math.copysign(1, pop)
    for expression, error in (
        ("pop / 0", ZeroDivisionError),
        ("pop +", ExprError),
        ("unknown", ExprError),
    ):
        with pytest.raises(error):
            effects.resolve_probability(expression, state, data)
    assert (
        effects.resolve_probability("pop < 1", GameState(2, 10, 10**400, 3, 2, 0), data)
        == 0
    )
