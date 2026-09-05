from dataclasses import replace
from statistics import mean, variance

import pytest

from justice_sim.models.offer import OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import ActionScore, RolloutPlanner

pytestmark = pytest.mark.unit


def test_adaptive_sampling_includes_uncertain_third_action(data_factory):
    planner = RolloutPlanner.from_defaults(data_factory())
    scores = [
        ActionScore("approve", 10, 0, 0, 0, 200),
        ActionScore("reject", 9, 0, 0, 0, 200),
        ActionScore("dismiss", 8, 0, 0, 10000, 200),
    ]
    assert planner._adaptive_actions(scores, ("approve", "reject", "dismiss")) == (
        "approve",
        "dismiss",
    )


def test_paired_uncertainty_is_checked_for_each_contender(data_factory):
    planner = RolloutPlanner.from_defaults(data_factory())
    samples = {
        "approve": (0, 20, 0, 20),
        "reject": (-1, 19, -1, 19),
        "dismiss": (18, -2, 18, -2),
    }
    scores = [
        ActionScore(action, mean(values), 0, 0, variance(values), len(values), values)
        for action, values in samples.items()
    ]
    # Reject is always one point worse. Dismiss has the same marginal variance
    # but its paired differences leave it a plausible winner.
    assert planner._adaptive_actions(scores, tuple(samples)) == ("approve", "dismiss")


def test_changed_leader_rechecks_unsampled_contenders(data_factory, monkeypatch):
    data = data_factory()
    offer = replace(data.offers[0], approve=OutcomeSpec(), reject=OutcomeSpec())
    planner = RolloutPlanner.from_defaults(data)
    planner.config = replace(
        planner.config,
        rollouts_per_action=5,
        adaptive_rollouts=True,
        adaptive_rollouts_max=10,
    )
    initial = {"approve": (10,) * 5, "reject": (7, 9, 11, 7, 11), "dismiss": (8,) * 5}
    additions = {"approve": (0,) * 5, "reject": (0,) * 5, "dismiss": (8,) * 5}
    calls = []

    def score(state, offer, rollouts, *, progress, actions, rollout_start=0):
        calls.append((actions, rollout_start, rollouts))
        samples = additions if rollout_start else initial
        return [
            ActionScore(
                action,
                mean(samples[action]),
                0,
                0,
                variance(samples[action]),
                len(samples[action]),
                samples[action],
            )
            for action in actions
        ]

    monkeypatch.setattr(planner, "_score_actions", score)
    recommendation = planner.recommend(GameState(1, 100, 3, 3, 1, 0), offer)
    assert calls == [
        (("approve", "reject", "dismiss"), 0, 5),
        (("approve", "reject"), 5, 5),
        (("dismiss",), 5, 5),
    ]
    assert recommendation.best_action == "dismiss"
    assert all(score.sample_count == 10 for score in recommendation.action_scores)
