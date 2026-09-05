"""Probe caching must agree with full reductions, including across cache hits."""

from dataclasses import replace
import pickle

import pytest

from justice_sim.engine import reducer
from justice_sim.engine.health import HealthProbeCache
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import BernoulliSpec, EffectSpec, OutcomeSpec
from justice_sim.models.state import (
    ActionTrigger,
    EncounterTrigger,
    GameState,
    ScheduledEvent,
    StatusEffect,
)

pytestmark = pytest.mark.unit


def reference(state, offer, action, data):
    try:
        result, _ = reducer.apply_action(state, offer, action, data, Rng(0))
    except reducer.ActionNotAllowed:
        return False
    return result.mh >= state.mh and not result.ended


@pytest.mark.parametrize(
    "title",
    ["Scripticus: Kitchen Loan", "Ghost: Scare Permit", "Honcho: 15-Day Return"],
)
def test_active_agreements_match_full_actions(builtin_data, title):
    state = GameState(11, 50, 20, 8, 2, 0)
    contract = next(o for o in builtin_data.offers if o.title == title)
    pending, _ = reducer.apply_action(state, contract, "approve", builtin_data, Rng(42))
    cache = HealthProbeCache(builtin_data)
    for case in (15, 25, 30):
        for variation in (
            replace(state, case_index=case),
            replace(pending, case_index=case),
        ):
            for offer in builtin_data.offers:
                for action in offer.actions_available:
                    assert cache.can_preserve_health(
                        variation, offer, action
                    ) == reference(variation, offer, action, builtin_data), (
                        title,
                        offer.title,
                        action,
                    )


def test_cache_matches_full_actions_across_resources_and_history(builtin_data):
    cache = HealthProbeCache(builtin_data)
    for case in (5, 15, 40):
        for coins, pop, mh, dismissals in (
            (0, 0, 1, 0),
            (4, 2, 3, 1),
            (50, 20, 8, 2),
            (4.5, 2.5, 1.4, 0.5),
        ):
            state = GameState(case, coins, pop, mh, dismissals, 0)
            for variation in (
                state,
                replace(
                    state,
                    counters={"timmy_rejects": 3, "harbinger_broke_stage": 1},
                    flags=frozenset({"test"}),
                    retirement_chests=10,
                ),
                replace(state, resource_floors={"mh": 3, "coins": 10}),
                replace(
                    state,
                    statuses={
                        "cannot_dismiss_harbinger": StatusEffect(
                            "cannot_dismiss_harbinger", -1
                        )
                    },
                ),
                replace(state, ended=True),
            ):
                for offer in builtin_data.offers:
                    for action in offer.actions_available:
                        assert cache.can_preserve_health(
                            variation, offer, action
                        ) == reference(variation, offer, action, builtin_data), (
                            offer.title,
                            action,
                            variation,
                        )
    assert cache._cache


def test_cache_reuses_irrelevant_state_and_keeps_payment_boundary(
    builtin_data, monkeypatch
):
    offer = next(o for o in builtin_data.offers if o.title == "Harbinger: Heart Attack")
    cache = HealthProbeCache(builtin_data)
    state = GameState(15, 100, 20, 3, 2, 0)
    calls = []
    original = reducer.action_preserves_health

    def counted(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(reducer, "action_preserves_health", counted)
    assert cache.can_preserve_health(state, offer, "approve")
    irrelevant = replace(
        state,
        pop=90,
        dismissals=0,
        retirement_chests=20,
        counters={"history": 100},
        action_triggers=(
            ActionTrigger("approve", (EffectSpec("end_run", {}),), npc_id="other"),
        ),
        scheduled_events=(ScheduledEvent(17, (EffectSpec("end_run", {}),)),),
    )
    assert cache.can_preserve_health(irrelevant, offer, "approve")
    assert len(calls) == 1
    assert not cache.can_preserve_health(replace(state, coins=0), offer, "approve")
    assert len(calls) == 2


@pytest.mark.parametrize("kind", ["action", "arrival", "event", "required", "blocked"])
def test_live_contracts_and_blocks_cannot_use_an_unrelated_cached_result(
    builtin_data, kind
):
    offer = next(o for o in builtin_data.offers if o.title == "Harbinger: Heart Attack")
    state = GameState(15, 100, 20, 3, 2, 0)
    fatal = (EffectSpec("end_run", {}),)
    changes = {
        "action": {"action_triggers": (ActionTrigger("approve", fatal),)},
        "arrival": {"encounter_triggers": (EncounterTrigger(fatal),)},
        "event": {"scheduled_events": (ScheduledEvent(16, fatal),)},
        "required": {
            "required_action": "reject",
            "required_action_penalty_effects": fatal,
        },
        "blocked": {"statuses": {"cannot_approve": StatusEffect("cannot_approve", -1)}},
    }
    cache = HealthProbeCache(builtin_data)
    assert cache.can_preserve_health(state, offer, "approve")
    changed = replace(state, **changes[kind])
    assert not reference(changed, offer, "approve", builtin_data)
    assert not cache.can_preserve_health(changed, offer, "approve")


@pytest.mark.parametrize(
    "kind", ["formula", "condition", "scaling", "random", "saved-counter"]
)
def test_custom_dependencies_bypass_narrow_cache(data_factory, kind):
    data = data_factory()
    effect = EffectSpec("add_resource", {"resource": "mh", "amount": "-pop"})
    if kind == "condition":
        effect = replace(
            effect, params={"resource": "mh", "amount": -1}, when="pop > 0"
        )
    if kind == "scaling":
        data = replace(
            data,
            special_rules=replace(
                data.special_rules,
                case_scale=replace(data.special_rules.case_scale, expr="pop"),
            ),
        )
        effect = replace(
            effect,
            params={"resource": "mh", "amount": {"expr": "-1", "scaling": "case"}},
        )
    if kind == "saved-counter":
        effect = replace(effect, params={"resource": "mh", "amount": "-counters.saved"})
    outcome = OutcomeSpec(effects=(effect,))
    if kind == "random":
        outcome = OutcomeSpec(random=BernoulliSpec("bernoulli", 1, (effect,), ()))
    offer = replace(data.offers[0], payment_resource="none", approve=outcome)
    data = replace(data, offers=(offer,), offers_by_id={offer.id: offer})
    cache = HealthProbeCache(data)
    for value in (0, 1, 2):
        state = GameState(5, 100, value, 3, 2, 0, counters={"saved": value})
        assert cache.can_preserve_health(state, offer, "approve") == reference(
            state, offer, "approve", data
        )
    assert not cache._cache


def test_cache_is_bounded_and_replaced_offers_bypass_profiles(builtin_data):
    cache = HealthProbeCache(builtin_data, max_entries=2)
    offer = next(o for o in builtin_data.offers if o.title == "Harbinger: Heart Attack")
    for coins in (0, 5, 100):
        state = GameState(5, coins, 0, 3, 0, 0)
        assert cache.can_preserve_health(state, offer, "approve") == reference(
            state, offer, "approve", builtin_data
        )
    assert len(cache._cache) == 2
    changed = replace(offer, approve=OutcomeSpec((EffectSpec("end_run", {}),)))
    assert not cache.can_preserve_health(state, changed, "approve")


def test_cache_remains_usable_after_worker_serialization(builtin_data, monkeypatch):
    cache = HealthProbeCache(builtin_data)
    offer = next(o for o in builtin_data.offers if o.title == "Harbinger: Heart Attack")
    state = GameState(5, 100, 20, 3, 0, 0)
    assert cache.can_preserve_health(state, offer, "approve")
    restored = pickle.loads(pickle.dumps(cache))

    def unexpected(*args):
        pytest.fail("Serialized probe cache should retain usable profiles and entries")

    monkeypatch.setattr(reducer, "action_preserves_health", unexpected)
    assert restored.can_preserve_health(
        state, restored.data.offers_by_id[offer.id], "approve"
    )
