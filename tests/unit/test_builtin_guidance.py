"""Behavioral checks for guidance applied inside recommendation rollouts."""

from dataclasses import replace

import pytest

from justice_sim.config import load_builtin_suggested_rules
from justice_sim.engine.rng import Rng
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import RolloutPlanner
from justice_sim.engine.scoring import weights_for_preset

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("preset", ["safe", "balanced", "greedy"])
@pytest.mark.parametrize("mh,expected", [(1, "approve"), (2, "reject")])
def test_cool_bird_values_safe_health_gain_without_disabling_caution(
    builtin_data, preset, mh, expected
):
    planner = RolloutPlanner.from_defaults(
        builtin_data, load_builtin_suggested_rules(builtin_data), seed=42
    )
    planner.config = replace(planner.config, risk_preset=preset)
    planner.weights = weights_for_preset(preset)
    offer = next(o for o in builtin_data.offers if o.title == "Cool Bird: Sanity Flip")
    state = GameState(1, 5, 3, mh, 0, 0)
    results = planner._exact_action_results(state, offer, "approve")
    assert sorted((s.mh, p) for s, p in results) == [
        (mh if mh == 1 else 1, 0.5),
        (mh + 2, 0.5),
    ]
    # At MH 1 the downside is empty; at MH 2 it enters the low-health penalty.
    # Root rollouts use this policy even with future cases remaining.
    for remaining in (0, 19):
        rng = Rng(42)
        assert (
            planner._select_action(state, offer, rng, remaining=remaining) == expected
        )
        assert rng.state().draws == 0
