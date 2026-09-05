"""Balanced policy keeps cash choices proportionate to projected injury risk."""

from dataclasses import replace

import pytest

from justice_sim.config import load_builtin_suggested_rules
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import weights_for_preset
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "preset,expected", [("balanced", "reject"), ("safe", "approve")]
)
def test_cash_poor_fine_choice_retains_distinct_risk_preferences(
    builtin_data, preset, expected
):
    planner = RolloutPlanner.from_defaults(
        builtin_data, load_builtin_suggested_rules(builtin_data), seed=42
    )
    planner.config = replace(planner.config, risk_preset=preset)
    planner.weights = weights_for_preset(preset)
    offer = next(
        o for o in builtin_data.offers if o.title == "Reanimated Hand: Waive the Fine"
    )
    state = GameState(11, 1, 3, 3, 0, 2)
    # Waiving buys popularity and slightly reduces projected injury risk.
    # Collecting gives six coins. Balanced accepts that trade; safe still
    # prioritizes the reduced risk. Neither action sacrifices health now.
    approved = planner._exact_action_results(state, offer, "approve")[0][0]
    rejected = planner._exact_action_results(state, offer, "reject")[0][0]
    assert (approved.coins, approved.pop, approved.mh) == (1, 6, 3)
    assert (rejected.coins, rejected.pop, rejected.mh) == (7, 0, 3)
    assert planner._select_action(state, offer, Rng(42), remaining=19) == expected
