from pathlib import Path

import pytest

from justice_sim.config import load_data
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import RolloutPlanner


@pytest.mark.unit
def test_planner_smoke_returns_recommendation():
    data_path = Path(__file__).parent.parent / "fixtures" / "tiny_data.json"
    data = load_data(data_path)
    planner = RolloutPlanner.from_defaults(data)
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )

    recommendation = planner.recommend(state, data.offers_by_id["offer_1"])

    assert recommendation.best_action in {"approve", "reject"}
    assert recommendation.action_scores
