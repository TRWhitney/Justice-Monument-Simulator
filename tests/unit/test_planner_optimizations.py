"""Equivalence checks for optimized scoring and deterministic transitions."""

from dataclasses import replace

import pytest

from justice_sim.engine import scoring
from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    action_preserves_health,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import (
    GameState,
    ScheduledEvent,
    StatusEffect,
)

pytestmark = pytest.mark.unit


def _reference_health(state, offer, action, data):
    result, _ = apply_action(state, offer, action, data, Rng(0))
    return result.mh >= state.mh and not result.ended


@pytest.mark.parametrize(
    "case,coins,pop,mh,dismissals",
    [
        (1, 0, 0, 1, 0),
        (5, 4, 0, 2, 1),
        (15, 11, 3, 1, 0),
        (15, 12, 20, 3, 2),
        (31, 100, 40, 8, 4),
        (5, 10.5, 2.5, 3.4, 1),
    ],
)
def test_health_probe_matches_every_builtin_action(
    builtin_data, case, coins, pop, mh, dismissals
):
    state = GameState(case, coins, pop, mh, dismissals, 2)
    for offer in builtin_data.offers:
        for action in offer.actions_available:
            try:
                expected = _reference_health(state, offer, action, builtin_data)
            except ActionNotAllowed:
                with pytest.raises(ActionNotAllowed):
                    action_preserves_health(state, offer, action, builtin_data)
            else:
                assert (
                    action_preserves_health(state, offer, action, builtin_data)
                    == expected
                ), (offer.title, action)


@pytest.mark.parametrize(
    "title",
    [
        "Scripticus: Kitchen Loan",
        "Ghost: Scare Permit",
        "Honcho: 15-Day Return",
    ],
)
def test_health_probe_matches_active_commitments(builtin_data, title):
    state = GameState(11, 50, 20, 8, 2, 0)
    contract = next(o for o in builtin_data.offers if o.title == title)
    state, _ = apply_action(state, contract, "approve", builtin_data, Rng(42))
    state = replace(state, case_index=15, resource_floors={"mh": 2})
    for offer in builtin_data.offers:
        for action in offer.actions_available:
            try:
                expected = _reference_health(state, offer, action, builtin_data)
            except ActionNotAllowed:
                continue
            assert (
                action_preserves_health(state, offer, action, builtin_data) == expected
            )


def test_health_probe_reuses_random_preparation(data_factory):
    data = data_factory()
    offer = replace(
        data.offers[0],
        arrival_effects=(
            EffectSpec(
                "random_range_resource", {"resource": "coins", "min": 0, "max": 8}
            ),
        ),
        approve=OutcomeSpec(
            effects=(
                EffectSpec(
                    "random_range_resource", {"resource": "mh", "min": -2, "max": 2}
                ),
            )
        ),
    )
    for coins in (0, 5, 10):
        state = GameState(1, coins, 3, 3, 0, 0)
        assert action_preserves_health(
            state, offer, "approve", data
        ) == _reference_health(state, offer, "approve", data)


def test_health_probe_checks_unpaid_penalty_after_preparation(builtin_data):
    offer = builtin_data.offers_by_id[builtin_data.special_rules.harbinger.offer_id]
    state = GameState(
        5,
        5,
        3,
        3,
        0,
        0,
        required_action="reject",
        required_action_penalty_effects=(
            EffectSpec("add_resource", {"resource": "coins", "amount": -3}),
        ),
    )
    assert _reference_health(state, offer, "approve", builtin_data) is False
    assert action_preserves_health(state, offer, "approve", builtin_data) is False


@pytest.mark.parametrize(
    "accessor",
    ["counters . saved_cost", "(counters).saved_cost", "counters\\\n.saved_cost"],
)
def test_risk_cache_reuses_history_but_preserves_saved_counter_dependencies(
    builtin_data,
    accessor,
):
    evaluator = scoring.RiskEvaluator(builtin_data)
    state = GameState(15, 100, 20, 3, 2, 0)
    original = evaluator.client_risk(state)
    assert (
        evaluator.client_risk(replace(state, counters={"unread_history": 12}))
        == original
    )
    assert len(evaluator._cache) == 1
    event = ScheduledEvent(16, (EffectSpec("end_run", {}, when=f"{accessor} > 0"),))
    pending = replace(state, scheduled_events=(event,), counters={"saved_cost": 0})
    costly = replace(pending, counters={"saved_cost": 1})
    assert evaluator.client_risk(pending) == scoring._client_harbinger_risk(
        pending, builtin_data
    )
    assert evaluator.client_risk(costly) == scoring._client_harbinger_risk(
        costly, builtin_data
    )
    assert evaluator.client_risk(pending) != evaluator.client_risk(costly)
    blocked = replace(
        state, statuses={"cannot_approve": StatusEffect("cannot_approve", -1)}
    )
    assert evaluator.client_risk(blocked) == scoring._client_harbinger_risk(
        blocked, builtin_data
    )


def test_risk_cache_is_bounded_and_data_specific(builtin_data):
    evaluator = scoring.RiskEvaluator(builtin_data, max_entries=2)
    for coins in range(4):
        state = GameState(15, coins, 0, 3, 0, 0)
        assert evaluator.client_risk(state) == scoring._client_harbinger_risk(
            state, builtin_data
        )
    assert len(evaluator._cache) == 2
