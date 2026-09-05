"""Deterministic transition reuse must preserve complete rollout RNG streams."""

from dataclasses import replace

import pytest

from justice_sim.engine import reducer, scoring
from justice_sim.engine.reducer import apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import BernoulliSpec, EffectSpec, OutcomeSpec
from justice_sim.models.state import ForcedEncounter, GameState
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


def _reference_health(state, offer, action, data):
    result, _ = apply_action(state, offer, action, data, Rng(0))
    return result.mh >= state.mh and not result.ended


@pytest.mark.parametrize(
    "outcome",
    [
        OutcomeSpec(random=BernoulliSpec("bernoulli", 1, (), ())),
        OutcomeSpec(
            effects=(
                EffectSpec(
                    "random_range_resource", {"resource": "coins", "min": 0, "max": 0}
                ),
            )
        ),
    ],
)
def test_single_branch_random_transition_still_consumes_draw(data_factory, outcome):
    data = data_factory()
    offer = replace(data.offers[0], actions_available=("approve",), approve=outcome)
    data = replace(data, offers_by_id={**data.offers_by_id, offer.id: offer})
    state = GameState(
        1, 5, 3, 3, 0, 0, forced_encounters=(ForcedEncounter(1, offer.id),)
    )
    planner = RolloutPlanner.from_defaults(data, seed=42)
    rng = Rng(42)
    result = planner._simulate_future(state, rng, 1)
    assert result.case_index == 2
    assert rng.state().draws == 1


@pytest.mark.parametrize("title", ["Scripticus: Kitchen Loan", "Honcho: 15-Day Return"])
def test_optimized_rollouts_match_full_reducer_and_rng(
    builtin_data, monkeypatch, title
):
    from justice_sim.config import load_builtin_suggested_rules

    rules = load_builtin_suggested_rules(builtin_data)
    state = GameState(11, 50, 20, 8, 2, 0)
    offer = next(o for o in builtin_data.offers if o.title == title)
    planner = RolloutPlanner.from_defaults(builtin_data, rules, seed=42)
    planner.config = replace(
        planner.config, horizon_cases=16, rollouts_per_action=2, adaptive_rollouts=False
    )
    optimized = planner.recommend(state, offer)
    optimized_rng = Rng(123)
    optimized_future = planner._simulate_future(state, optimized_rng, 16)
    choose = planner._choose_action

    def without_transition(*args, **kwargs):
        return choose(*args, **kwargs)[0], None

    monkeypatch.setattr(planner, "_choose_action", without_transition)
    monkeypatch.setattr(reducer, "action_preserves_health", _reference_health)
    monkeypatch.setattr(
        scoring.RiskEvaluator,
        "client_risk",
        lambda self, s: scoring._client_harbinger_risk(s, self.data),
    )
    planner.reset_cache()
    reference = planner.recommend(state, offer)
    assert optimized == reference
    assert [s.utility_samples for s in optimized.action_scores] == [
        s.utility_samples for s in reference.action_scores
    ]
    reference_rng = Rng(123)
    assert planner._simulate_future(state, reference_rng, 16) == optimized_future
    assert reference_rng.state() == optimized_rng.state()
