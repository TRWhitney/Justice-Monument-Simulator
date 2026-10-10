"""Exact pool safety reuse must preserve probability arithmetic and fallbacks."""

from dataclasses import replace

import pytest

from justice_sim.engine import scoring
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import EncounterTrigger, GameState

pytestmark = pytest.mark.unit


def test_pool_safety_reuses_payment_regions_with_live_popularity(
    builtin_data, monkeypatch
):
    evaluator = scoring.RiskEvaluator(builtin_data)
    calls = []
    original = evaluator._health_probes.can_preserve_health

    def counted(state, offer, action):
        calls.append((offer.id, action))
        return original(state, offer, action)

    monkeypatch.setattr(evaluator._health_probes, "can_preserve_health", counted)
    state = GameState(15, 2, 20, 3, 0, 0)
    first = evaluator.client_risk(state)
    count = len(calls)
    second_state = replace(state, coins=3, pop=21, retirement_chests=10)
    second = evaluator.client_risk(second_state)
    assert count > 0 and len(calls) == count
    assert first != second
    assert first == scoring._client_harbinger_risk(state, builtin_data)
    assert second == scoring._client_harbinger_risk(second_state, builtin_data)


def test_pool_safety_reuses_condition_regions(builtin_data, monkeypatch):
    evaluator = scoring.RiskEvaluator(builtin_data)
    calls = []
    original = evaluator._health_probes.can_preserve_health

    def counted(state, offer, action):
        calls.append((offer.id, action))
        return original(state, offer, action)

    monkeypatch.setattr(evaluator._health_probes, "can_preserve_health", counted)
    state = GameState(15, 2, 20, 3, 0, 0, counters={"timmy_rejects": 3})
    expected = evaluator.client_risk(state)
    count = len(calls)
    changed = replace(state, counters={"timmy_rejects": 9}, flags=frozenset({"unread"}))
    assert evaluator.client_risk(changed) == expected
    assert count > 0 and len(calls) == count


def test_pool_safety_ignores_nonmatching_contract_payloads(builtin_data, monkeypatch):
    evaluator = scoring.RiskEvaluator(builtin_data)
    calls = []
    original = evaluator._health_probes.can_preserve_health

    def counted(state, offer, action):
        calls.append((offer.id, action))
        return original(state, offer, action)

    monkeypatch.setattr(evaluator._health_probes, "can_preserve_health", counted)
    trigger = EncounterTrigger(
        (EffectSpec("add_resource", {"resource": "coins", "amount": 10}),),
        npc_id="scripticus",
        label="scripticus_loan",
    )
    state = GameState(15, 2, 20, 3, 0, 0, encounter_triggers=(trigger,))
    expected = evaluator.client_risk(state)
    count = len(calls)
    changed = replace(state, encounter_triggers=(replace(trigger, remaining_uses=9),))
    assert evaluator.client_risk(changed) == expected
    assert count > 0 and len(calls) == count


def test_simple_pool_reuse_avoids_full_state_serialization(builtin_data, monkeypatch):
    evaluator = scoring.RiskEvaluator(builtin_data)
    state = GameState(15, 2, 20, 3, 0, 0)
    expected = scoring._client_harbinger_risk(state, builtin_data)

    def unexpected(*args, **kwargs):
        pytest.fail("Proved pool safety does not need full contract serialization")

    monkeypatch.setattr(GameState, "contract_key", unexpected)
    assert evaluator.client_risk(state) == expected


def test_inactive_case_only_arrival_reuses_pool_safety(builtin_data, monkeypatch):
    evaluator = scoring.RiskEvaluator(builtin_data)
    calls = []
    original = evaluator._health_probes.can_preserve_health

    def counted(state, offer, action):
        calls.append((offer.id, action))
        return original(state, offer, action)

    monkeypatch.setattr(evaluator._health_probes, "can_preserve_health", counted)
    trigger = EncounterTrigger(
        (EffectSpec("add_resource", {"resource": "pop", "amount": -3}),),
        when="case_index % 5 != 0",
        label="ghost_scare_pop",
    )
    state = GameState(15, 2, 20, 3, 0, 0, encounter_triggers=(trigger,))
    expected = evaluator.client_risk(state)
    count = len(calls)
    changed = replace(state, coins=3, pop=21)
    assert evaluator.client_risk(changed) == scoring._client_harbinger_risk(
        changed, builtin_data
    )
    assert expected == scoring._client_harbinger_risk(state, builtin_data)
    assert count > 0 and len(calls) == count


def test_base_unpaid_boundary_is_preserved_with_noncoin_payment(data_factory):
    data = data_factory(include_grateful=False)
    base_id = data.special_rules.harbinger.offer_id
    offers = tuple(replace(o, payment_resource="none") for o in data.offers)
    data = replace(
        data,
        offers=offers,
        offers_by_id={o.id: o for o in offers},
        special_rules=replace(
            data.special_rules,
            client_encounters=True,
            harbinger=replace(
                data.special_rules.harbinger,
                on_unpaid_effects=(
                    EffectSpec("add_resource", {"resource": "mh", "amount": -1}),
                ),
            ),
        ),
    )
    evaluator = scoring.RiskEvaluator(data)
    state = GameState(5, 0, 0, 3, 0, 0)
    assert data.offers_by_id[base_id].payment_resource == "none"
    for coins in (0, 5, 4.999, 5.001):
        changed = replace(state, coins=coins)
        assert evaluator.client_risk(changed) == scoring._client_harbinger_risk(
            changed, data
        )


def test_pool_risk_matches_full_reducer_at_payments_conditions_and_floors(builtin_data):
    from justice_sim.engine.effects import outcome_additive_resource_cost
    from justice_sim.engine.encounter import (
        client_encounter_probabilities,
        UniformEncounterModel,
    )
    from justice_sim.engine.reducer import ActionNotAllowed, apply_action
    from justice_sim.engine.rng import Rng
    from justice_sim.models.state import StatusEffect

    evaluator = scoring.RiskEvaluator(builtin_data)
    for case in (5, 15, 40):
        root = GameState(case, 0, 0, 3, 0, 0)
        costs = {
            outcome_additive_resource_cost(root, o.approve, "coins", builtin_data)
            for o in evaluator._pool_safety.offers
        }
        for amount in sorted(
            {0, 0.5, 100, *(x + d for x in costs for d in (-0.001, 0, 0.001))}
        ):
            state = replace(root, coins=amount, pop=amount)
            for variation in (
                state,
                replace(state, dismissals=0.5),
                replace(state, resource_floors={"mh": 3, "coins": 20}),
                replace(
                    state, counters={"timmy_rejects": 3, "harbinger_broke_stage": 1}
                ),
                replace(
                    state,
                    statuses={
                        "cannot_dismiss_harbinger": StatusEffect(
                            "cannot_dismiss_harbinger", -1
                        )
                    },
                ),
            ):
                risk = 0.0
                for key, probability in client_encounter_probabilities(
                    variation, builtin_data, UniformEncounterModel()
                ).items():
                    offer = builtin_data.offers_by_id[key]
                    safe = False
                    for action in offer.actions_available:
                        try:
                            result, _ = apply_action(
                                variation, offer, action, builtin_data, Rng(0)
                            )
                            safe |= result.mh >= variation.mh and not result.ended
                        except ActionNotAllowed:
                            pass
                    if not safe:
                        risk += probability
                assert evaluator.client_risk(variation) == risk


@pytest.mark.parametrize(
    "kind", ["arrival", "guard", "action", "event", "required", "forced", "override"]
)
def test_complex_states_do_not_reuse_plain_pool_safety(builtin_data, kind):
    from justice_sim.models.state import (
        ActionTrigger,
        ScheduledEvent,
        ForcedEncounter,
        EncounterOverride,
    )

    evaluator = scoring.RiskEvaluator(builtin_data)
    state = GameState(15, 100, 20, 3, 0, 0)
    evaluator.client_risk(state)
    harm = (EffectSpec("add_resource", {"resource": "mh", "amount": -2}),)
    changes = {
        "arrival": {"encounter_triggers": (EncounterTrigger(harm),)},
        "guard": {"encounter_triggers": (EncounterTrigger(harm, when="coins > 0"),)},
        "action": {"action_triggers": (ActionTrigger("any", harm),)},
        "event": {"scheduled_events": (ScheduledEvent(16, harm),)},
        "required": {
            "required_action": "reject",
            "required_action_penalty_effects": harm,
        },
        "forced": {
            "forced_encounters": (ForcedEncounter(15, builtin_data.offers[0].id),)
        },
        "override": {
            "encounter_overrides": (
                EncounterOverride(
                    offer_id=builtin_data.offers[0].id, allow_harbinger=True
                ),
            )
        },
    }
    changed = replace(state, **changes[kind])
    assert evaluator.client_risk(changed) == scoring._client_harbinger_risk(
        changed, builtin_data
    )
    assert evaluator._cache


@pytest.mark.parametrize(
    "predicate",
    [
        "coins > pop",
        "coins + 1 > 5",
        "has_flag('ready')",
        "has_status('ready')",
        "has_pending('ready')",
        "counters.timmy_rejects + 1 > 4",
    ],
)
def test_custom_conditions_keep_all_live_dependencies(builtin_data, predicate):
    from justice_sim.models.state import ScheduledEvent, StatusEffect

    pool = builtin_data.special_rules.harbinger.offer_pool
    target = pool[0]
    offers = tuple(
        replace(o, conditions=(predicate,)) if o.id == target else o
        for o in builtin_data.offers
    )
    data = replace(builtin_data, offers=offers, offers_by_id={o.id: o for o in offers})
    evaluator = scoring.RiskEvaluator(data)
    state = GameState(15, 1, 2, 3, 0, 0)
    for variation in (
        state,
        replace(state, coins=6, pop=5),
        replace(state, flags=frozenset({"ready"})),
        replace(state, statuses={"ready": StatusEffect("ready", -1)}),
        replace(state, scheduled_events=(ScheduledEvent(20, (), label="ready"),)),
        replace(state, counters={"timmy_rejects": 4}),
    ):
        assert evaluator.client_risk(variation) == scoring._client_harbinger_risk(
            variation, data
        )


def test_pool_cache_is_bounded_disabled_and_serializable(builtin_data):
    import pickle

    evaluator = scoring.RiskEvaluator(builtin_data, max_entries=2)
    for case in (5, 15, 20, 30):
        state = GameState(case, 50, 20, 3, 0, 0)
        assert evaluator.client_risk(state) == scoring._client_harbinger_risk(
            state, builtin_data
        )
    assert len(evaluator._pool_safety._cache) == 2
    assert len(evaluator._pool_safety._case_boundaries) == 2
    restored = pickle.loads(pickle.dumps(evaluator))
    assert restored.client_risk(state) == evaluator.client_risk(state)
    disabled = scoring.RiskEvaluator(builtin_data, max_entries=0)
    assert disabled.client_risk(state) == evaluator.client_risk(state)
    assert not disabled._pool_safety._cache and not disabled._cache


@pytest.mark.parametrize("kind", ["arrival", "formula", "random"])
def test_unsupported_pool_definitions_use_full_reducer(builtin_data, kind):
    from justice_sim.models.offer import BernoulliSpec, OutcomeSpec

    target = builtin_data.special_rules.harbinger.offer_pool[0]
    original = builtin_data.offers_by_id[target]
    harm = EffectSpec("add_resource", {"resource": "mh", "amount": "-pop"})
    if kind == "arrival":
        changed = replace(
            original,
            arrival_effects=(
                EffectSpec("add_resource", {"resource": "coins", "amount": 5}),
            ),
        )
    elif kind == "formula":
        changed = replace(original, approve=OutcomeSpec((harm,)))
    else:
        changed = replace(
            original,
            approve=OutcomeSpec(random=BernoulliSpec("bernoulli", 0.5, (harm,), ())),
        )
    offers = tuple(changed if o.id == target else o for o in builtin_data.offers)
    data = replace(builtin_data, offers=offers, offers_by_id={o.id: o for o in offers})
    evaluator = scoring.RiskEvaluator(data)
    for pop in (0, 1, 50):
        state = GameState(15, 2, pop, 3, 0, 0)
        assert evaluator.client_risk(state) == scoring._client_harbinger_risk(
            state, data
        )
    assert evaluator._cache and not evaluator._pool_safety._cache
