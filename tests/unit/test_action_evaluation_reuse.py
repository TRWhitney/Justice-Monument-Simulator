"""Evaluate alternatives once and avoid scoring a choice that cannot change."""

from dataclasses import replace

import pytest

from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.models.suggested_rules import ActionConstraint
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("terminal", [False, True])
def test_recommendation_shortcuts_share_immediate_outcomes(
    data_factory, monkeypatch, terminal
):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    if terminal:
        outcome = OutcomeSpec((EffectSpec("end_run", {}),))
        offer = replace(offer, approve=outcome, reject=outcome, dismiss=outcome)
    planner = RolloutPlanner.from_defaults(data, seed=42)
    state = GameState(1, 5, 3, 3, 0, 0)
    calls = []
    original = planner._exact_action_results

    def counted(state, offer, action, **kwargs):
        calls.append(action)
        return original(state, offer, action, **kwargs)

    monkeypatch.setattr(planner, "_exact_action_results", counted)
    result = planner.recommend(state, offer)
    assert result.best_action == "approve"
    assert calls == list(offer.actions_available)
    assert all(score.sample_count == 0 for score in result.action_scores)


@pytest.mark.parametrize("constraint", [False, True])
def test_only_eligible_future_action_skips_utility(
    data_factory, monkeypatch, constraint
):
    data = data_factory()
    offer = data.offers_by_id["offer1"]
    if not constraint:
        offer = replace(offer, actions_available=("approve",))
    planner = RolloutPlanner.from_defaults(data, seed=42)
    if constraint:
        planner.suggested_rules = replace(
            planner.suggested_rules,
            constraints_by_offer={offer.id: (ActionConstraint("approve", "require"),)},
        )

    def unexpected(*args, **kwargs):
        pytest.fail("A sole eligible action does not need utility or policy sampling")

    monkeypatch.setattr(planner, "_cached_utility", unexpected)
    monkeypatch.setattr(planner, "_sample_action_value", unexpected)
    monkeypatch.setattr(planner, "_continuation_value", unexpected)
    rng = Rng(42)
    action, transition = planner._choose_action(
        GameState(1, 5, 3, 3, 0, 0), offer, rng, remaining=20
    )
    assert action == "approve"
    assert transition is not None and transition.coins == 7
    assert rng.state().draws == 0
