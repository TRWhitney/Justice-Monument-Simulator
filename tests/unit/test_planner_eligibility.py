from dataclasses import replace

import pytest

from justice_sim.engine.reducer import apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import BernoulliSpec, EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def test_promised_cool_bird_survives_both_branches_and_excludes_rejection(builtin_data):
    promise = next(
        o for o in builtin_data.offers if o.title == "Scripticus: Promise Me"
    )
    bird = next(o for o in builtin_data.offers if o.title == "Cool Bird: Sanity Flip")
    state, _ = apply_action(
        GameState(1, 5, 3, 1, 0, 0), promise, "approve", builtin_data, Rng(0)
    )
    planner = RolloutPlanner(
        builtin_data,
        PlannerConfig(horizon_cases=0, rollouts_per_action=4, adaptive_rollouts=False),
        seed=1,
    )
    results = planner._exact_action_results(state, bird, "approve")
    assert [(s.mh, p) for s, p in results] == [(3, 0.5), (1, 0.5)]
    progress = []
    recommendation = planner.recommend(state, bird, progress.append)
    assert recommendation.best_action == "approve"
    excluded = [s for s in recommendation.action_scores if s.action != "approve"]
    assert all(
        s.sample_count == 0 and s.expected_utility == float("-inf") for s in excluded
    )
    assert sum(progress) == 4


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


def test_any_survival_chance_beats_a_proven_fatal_reward(data_factory):
    data = data_factory()
    death = EffectSpec("add_resource", {"resource": "mh", "amount": -1})
    offer = replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=OutcomeSpec(
            effects=(
                EffectSpec(
                    "add_resource", {"resource": "retirement_chests", "amount": 100}
                ),
                death,
            )
        ),
        reject=OutcomeSpec(random=BernoulliSpec("bernoulli", 0.01, (), (death,))),
    )
    planner = RolloutPlanner(
        data,
        PlannerConfig(horizon_cases=0, rollouts_per_action=4, adaptive_rollouts=False),
        seed=1,
    )
    state = GameState(1, 5, 3, 1, 0, 0)
    assert planner.recommend(state, offer).best_action == "reject"


def test_all_fatal_options_still_have_exact_scores(data_factory):
    data = data_factory()
    death = EffectSpec("add_resource", {"resource": "mh", "amount": -1})
    offer = replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=OutcomeSpec(effects=(death,)),
        reject=OutcomeSpec(effects=(death,)),
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    result = planner.recommend(GameState(1, 5, 3, 1, 0, 0), offer)
    assert {s.action for s in result.action_scores} == {"approve", "reject"}
    assert all(
        s.death_probability == 1 and s.sample_count == 0 for s in result.action_scores
    )
