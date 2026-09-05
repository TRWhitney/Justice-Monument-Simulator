"""Regressions from the simulation audit, including real offer combinations."""

from dataclasses import replace

import pytest

from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    can_afford_action,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def _resource(resource, amount):
    return EffectSpec("add_resource", {"resource": resource, "amount": amount})


def _planner(data):
    return RolloutPlanner(
        data,
        PlannerConfig(horizon_cases=0, rollouts_per_action=16, adaptive_rollouts=False),
        seed=7,
    )


@pytest.mark.parametrize("debt_mode", ["clamp_to_zero", "allow_negative"])
@pytest.mark.parametrize("coins, affordable", [(10, False), (11, True), (12, True)])
def test_shark_attack_uses_rounded_payment(builtin_data, coins, affordable, debt_mode):
    data = replace(
        builtin_data, defaults=replace(builtin_data.defaults, debt_mode=debt_mode)
    )
    offer = next(o for o in data.offers if "shark_attack" in o.id)
    state = GameState(15, coins, 3, 1, 0, 0)
    assert can_afford_action(state, offer, "approve", data) is affordable
    if not affordable:
        with pytest.raises(ActionNotAllowed, match="Insufficient funds"):
            apply_action(state, offer, "approve", data, Rng(0))
        return
    result, _ = apply_action(state, offer, "approve", data, Rng(0))
    assert (result.coins, result.mh) == (coins - 11, 1)
    assert _planner(data).recommend(state, offer).best_action == "approve"


@pytest.mark.parametrize("scheduled", [False, True])
def test_affordability_does_not_charge_inactive_or_deferred_effects(
    data_factory, scheduled
):
    data = data_factory()
    effect = (
        replace(_resource("coins", -10), schedule_after_cases=2)
        if scheduled
        else replace(_resource("coins", -10), when="false")
    )
    offer = replace(data.offers[0], approve=OutcomeSpec(effects=(effect,)))
    state = GameState(1, 0, 0, 3, 0, 0)
    assert can_afford_action(state, offer, "approve", data)
    result, _ = apply_action(state, offer, "approve", data, Rng(0))
    assert result.coins == 0
    assert bool(result.scheduled_events) is scheduled
