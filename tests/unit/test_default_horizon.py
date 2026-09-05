from dataclasses import replace

import pytest

from justice_sim.engine.reducer import apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import OutcomeSpec
from justice_sim.models.state import ForcedEncounter, GameState
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


def test_builtin_default_horizon_includes_fifteen_day_return(builtin_data):
    investment = next(
        o for o in builtin_data.offers if o.title == "Honcho: 15-Day Return"
    )
    quiet = replace(
        investment,
        id="quiet",
        actions_available=("approve",),
        approve=OutcomeSpec(),
        payment_resource="none",
        conditions=(),
    )
    data = replace(
        builtin_data, offers_by_id={**builtin_data.offers_by_id, quiet.id: quiet}
    )
    state, _ = apply_action(
        GameState(11, 50, 20, 8, 2, 0), investment, "approve", data, Rng(42)
    )
    state = replace(
        state,
        forced_encounters=tuple(
            ForcedEncounter(case, quiet.id)
            for case in range(state.case_index, state.case_index + 20)
        ),
    )
    planner = RolloutPlanner.from_defaults(data, seed=42)
    assert planner.config.horizon_cases == 20
    assert planner.config.rollouts_per_action == 200
    assert planner.config.adaptive_rollouts_max == 400
    old_horizon = planner._simulate_future(state, Rng(42), 12)
    new_horizon = planner._simulate_future(state, Rng(42), planner.config.horizon_cases)
    assert any(e.label == "honcho_time" for e in old_horizon.scheduled_events)
    assert not any(e.label == "honcho_time" for e in new_horizon.scheduled_events)
    assert new_horizon.coins > old_horizon.coins
