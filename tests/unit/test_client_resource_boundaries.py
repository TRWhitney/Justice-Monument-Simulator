"""Resource-boundary fixtures checked against the official client action code."""

from dataclasses import replace
from io import StringIO

import pytest
from rich.console import Console

from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    apply_action_with_outcome,
    can_afford_action,
    preview_state_after_encounter_triggers,
    preview_state_before_outcome,
)
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import utility
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner
from justice_sim.ui_cli.cli import CliApp

pytestmark = pytest.mark.unit


def _offer(data, row):
    return next(o for o in data.offers if row in o.client_rows)


def _agreement(data, state, row):
    return apply_action(state, _offer(data, row), "approve", data, Rng(0))[0]


def _planner(data):
    return RolloutPlanner(
        data,
        PlannerConfig(horizon_cases=0, rollouts_per_action=8, adaptive_rollouts=False),
        seed=7,
    )


@pytest.mark.parametrize("pop", [0, 1, 2, 3])
def test_hand_preserves_arrival_debt_until_action_resolves(builtin_data, pop):
    state = _agreement(builtin_data, GameState(1, 10, 5, 5, 3, 7), 62)
    state = replace(state, coins=10, pop=pop)
    offer = _offer(builtin_data, 1)
    rng = Rng(7)
    prepared = preview_state_before_outcome(
        state, offer, "approve", builtin_data, Rng.from_state(rng.state())
    )
    assert (prepared.coins, prepared.pop) == (14, pop - 2)
    assert (state.coins, state.pop, rng.state().draws) == (10, pop, 0)
    result, _ = apply_action(state, offer, "approve", builtin_data, rng)
    manual, _ = apply_action_with_outcome(
        state, offer, "approve", offer.approve, builtin_data, Rng(7)
    )
    assert manual == result
    assert (result.coins, result.pop) == (14, max(0, pop - 1))


@pytest.mark.parametrize("agreement_order", [(62, 50), (50, 62)])
def test_ghost_clamps_before_hand_in_either_agreement_order(
    builtin_data, agreement_order
):
    state = GameState(1, 10, 5, 5, 3, 7)
    for row in agreement_order:
        state = _agreement(builtin_data, state, row)
    state = replace(state, case_index=4, coins=10, pop=0)
    offer = _offer(builtin_data, 1)
    preview = preview_state_after_encounter_triggers(state, offer, builtin_data, Rng(0))
    assert (preview.coins, preview.pop) == (14, -2)
    result, _ = apply_action(state, offer, "approve", builtin_data, Rng(0))
    assert (result.coins, result.pop) == (14, 0)


@pytest.fixture
def scare_with_floor(builtin_data):
    state = GameState(1, 20, 5, 5, 3, 7)
    for row in (58, 50):
        state = _agreement(builtin_data, state, row)
    return replace(state, case_index=21, coins=20, pop=5)


@pytest.mark.parametrize("action", ["reject", "dismiss"])
def test_popularity_floor_returns_only_after_action(
    builtin_data, scare_with_floor, action
):
    state = scare_with_floor
    offer = _offer(builtin_data, 22)
    preview = preview_state_after_encounter_triggers(state, offer, builtin_data, Rng(0))
    assert preview.pop == 4
    assert not can_afford_action(preview, offer, "approve", builtin_data)
    with pytest.raises(ActionNotAllowed, match="Insufficient funds"):
        apply_action(state, offer, "approve", builtin_data, Rng(0))
    result, _ = apply_action(state, offer, action, builtin_data, Rng(0))
    assert result.pop == 5
    assert result.retirement_chests == 7
    recommendation = _planner(builtin_data).recommend(state, offer)
    assert recommendation.best_action != "approve"
    blocked = next(s for s in recommendation.action_scores if s.action == "approve")
    assert blocked.expected_utility == float("-inf")
    assert blocked.sample_count == 0


def test_action_formula_uses_popularity_below_floor(builtin_data, scare_with_floor):
    # Arrival: 5 -> 4. Coin Swap adds ceil(min(4/3, 20*.3)) = 2, giving 6.
    result, _ = apply_action(
        scare_with_floor, _offer(builtin_data, 66), "approve", builtin_data, Rng(0)
    )
    assert (result.coins, result.pop) == (16, 6)


def test_ghost_own_zero_clamp_does_not_restore_permanent_floor(
    builtin_data, scare_with_floor
):
    state = replace(scare_with_floor, pop=0)
    offer = _offer(builtin_data, 80)
    preview = preview_state_after_encounter_triggers(state, offer, builtin_data, Rng(0))
    assert preview.pop == 0
    result, _ = apply_action(state, offer, "reject", builtin_data, Rng(0))
    assert result.pop == 5


def test_cli_rejects_approval_below_floor(builtin_data, scare_with_floor):
    app = CliApp(builtin_data, SuggestedRules.empty(), console=Console(file=StringIO()))
    app.sim_mode = "none"
    app.session.state = scare_with_floor
    app.current_offer = _offer(builtin_data, 22)
    assert app.handle_command("approve")
    assert app.session.state == scare_with_floor
    assert not app.session.log.entries
    assert app.handle_command("reject")
    assert app.session.state.pop == 5
    assert len(app.session.log.entries) == 1


def test_shortcut_still_scores_final_floor_without_rollouts(
    builtin_data, scare_with_floor
):
    planner = _planner(builtin_data)
    progress = []
    recommendation = planner.recommend(
        scare_with_floor, _offer(builtin_data, 80), progress=progress.append
    )
    assert recommendation.best_action == "approve"
    assert progress == []
    score = next(s for s in recommendation.action_scores if s.action == "approve")
    assert score.sample_count == 0
    assert score.expected_chests == pytest.approx(9.49)
    outcomes = [
        (replace(scare_with_floor, case_index=22, retirement_chests=9), 0.30),
        (replace(scare_with_floor, case_index=22, retirement_chests=10), 0.63),
        (replace(scare_with_floor, case_index=22, dismissals=5), 0.035),
        (replace(scare_with_floor, case_index=22, coins=22), 0.035),
    ]
    assert score.expected_utility == pytest.approx(
        sum(utility(s, builtin_data, planner.weights) * p for s, p in outcomes)
    )


@pytest.mark.parametrize("mh,remaining", [(1, 0), (5, 0), (999, 0), (1000, 1)])
def test_grateful_rejection_clamps_health_at_action_boundary(
    builtin_data, mh, remaining
):
    state = GameState(5, 20, 5, mh, 3, 7)
    offer = _offer(builtin_data, 25)
    result, _ = apply_action(state, offer, "reject", builtin_data, Rng(0))
    assert result.mh == remaining
    planner = _planner(builtin_data)
    expected = replace(state, case_index=6, mh=remaining)
    assert planner._expected_action_value(
        state, offer, "reject", Rng(0)
    ) == pytest.approx(utility(expected, builtin_data, planner.weights))


def test_explicit_debt_mode_preserves_negative_resources(builtin_data):
    data = replace(
        builtin_data,
        defaults=replace(builtin_data.defaults, debt_mode="allow_negative"),
    )
    result, _ = apply_action(
        GameState(5, 20, 5, 5, 3, 7), _offer(data, 25), "reject", data, Rng(0)
    )
    assert result.mh == -994
    state = _agreement(data, GameState(1, 10, 5, 5, 3, 7), 62)
    result, _ = apply_action(
        replace(state, pop=0), _offer(data, 1), "approve", data, Rng(0)
    )
    assert result.pop == -1


def test_custom_dataset_retains_per_effect_bounds(data_factory):
    data = data_factory()
    offer = replace(
        data.offers[0],
        reject=OutcomeSpec(
            effects=(
                EffectSpec("add_resource", {"resource": "pop", "amount": -10}),
                EffectSpec("add_resource", {"resource": "pop", "amount": 1}),
                EffectSpec("add_resource", {"resource": "mh", "amount": -999}),
            )
        ),
    )
    result, _ = apply_action(
        GameState(1, 10, 5, 5, 3, 7, resource_floors={"pop": 5}),
        offer,
        "reject",
        data,
        Rng(0),
    )
    assert (result.pop, result.mh) == (6, -994)
