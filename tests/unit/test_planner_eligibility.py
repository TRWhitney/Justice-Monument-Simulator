import pytest
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def test_fatal_and_unaffordable_paths_are_not_sampled(builtin_data, monkeypatch):
    offer = next(o for o in builtin_data.offers if o.title == "Harbinger: Shark Attack")
    state = GameState(5, 100, 0, 1, 0, 0)
    planner = RolloutPlanner(
        builtin_data,
        PlannerConfig(horizon_cases=1, rollouts_per_action=4, adaptive_rollouts=False),
        seed=1,
    )
    sampled = []
    simulate = planner._simulate_action

    def record(state, offer, action, *args, **kwargs):
        sampled.append(action)
        return simulate(state, offer, action, *args, **kwargs)

    monkeypatch.setattr(planner, "_simulate_action", record)
    progress = []
    planner.recommend(state, offer, progress.append)
    assert sampled == ["approve"]
    assert sum(progress) == planner.rollout_work_total(state, offer) == 4
