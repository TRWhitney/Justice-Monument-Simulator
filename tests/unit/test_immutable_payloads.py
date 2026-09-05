"""Cached contract keys own their nested input and survive serialization."""

from copy import deepcopy
from dataclasses import replace
import json
import pickle

import pytest

from justice_sim.engine.effects import apply_effects, resolve_expr, resolve_probability
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import (
    ActionTrigger,
    EncounterModifier,
    EncounterOverride,
    EncounterTrigger,
    GameState,
    ScheduledEvent,
    StatusEffect,
)
from justice_sim.persistence.runs import deserialize_state, serialize_state
from justice_sim.util.immutable import FrozenMapping, freeze_payload, thaw_payload

pytestmark = pytest.mark.unit


def test_owned_payload_blocks_nested_mutation_and_detaches_constructor_input():
    raw = {
        "effects": [{"params": {"amount": {"expr": "2", "snapshot": True}}}],
        "tags": {"a", "b"},
    }
    effect = EffectSpec("schedule_effects", raw)
    key = effect.cache_key
    raw["effects"][0]["params"]["amount"]["expr"] = "100"
    raw["effects"].append({})
    raw["tags"].add("c")
    assert effect.params["effects"][0]["params"]["amount"]["expr"] == "2"
    assert len(effect.params["effects"]) == 1
    assert effect.params["tags"] == frozenset({"a", "b"})
    assert effect.cache_key is key
    with pytest.raises(TypeError):
        effect.params["effects"][0]["params"]["amount"]["expr"] = "4"
    with pytest.raises(AttributeError):
        effect.params["effects"].append({})
    with pytest.raises(TypeError):
        effect.params._values = {}
    with pytest.raises(TypeError):
        del effect.params._values
    with pytest.raises(TypeError):
        effect.params._values["effects"] = ()
    assert deepcopy(effect.params) is effect.params


def test_resource_changes_reuse_contract_keys_but_replacements_get_new_keys():
    effect = EffectSpec("add_resource", {"resource": "coins", "amount": 2})
    event = ScheduledEvent(6, (effect,), "payout")
    state = GameState(5, 10, 2, 3, 1, 0, scheduled_events=(event,))
    original = state.to_cache_key()
    changed = replace(state, coins=20).to_cache_key()
    assert changed != original
    assert changed.scheduled_events[0] is original.scheduled_events[0]
    assert effect.cache_key is effect.cache_key
    altered = replace(
        event, effects=(replace(effect, params={"resource": "coins", "amount": 5}),)
    )
    assert altered.cache_key != event.cache_key
    assert replace(state, scheduled_events=(altered,)).to_cache_key() != original
    # These outer state mappings remain live and must never have memoized keys.
    state.counters["saved"] = 1
    assert state.to_cache_key() != original


def test_all_contract_payloads_own_their_input():
    data = {"nested": [{"value": 1}]}
    weights = {"npc": 2.0}
    probability = {"expr": "20", "format": "percent"}
    effects = [EffectSpec("noop", {})]
    status = StatusEffect("saved", 2, data)
    modifier = EncounterModifier(npc_weights=weights)
    override = EncounterOverride(probability=probability)
    action = ActionTrigger("approve", effects)
    encounter = EncounterTrigger(effects)
    event = ScheduledEvent(2, effects)
    data["nested"][0]["value"] = 9
    weights["npc"] = 99
    probability["expr"] = "100"
    effects.clear()
    assert status.data["nested"][0]["value"] == 1
    assert modifier.npc_weights["npc"] == 2
    assert override.probability["expr"] == "20"
    assert all(len(item.effects) == 1 for item in (action, encounter, event))


def test_nested_state_json_and_pickle_roundtrip_preserve_keys_and_ownership():
    effect = EffectSpec(
        "schedule_effects",
        {
            "after_cases": 2,
            "effects": [
                {
                    "type": "add_resource",
                    "params": {
                        "resource": "coins",
                        "amount": {"expr": "5", "snapshot": True},
                    },
                }
            ],
        },
    )
    state = GameState(
        5,
        10,
        3,
        3,
        1,
        0,
        statuses={"saved": StatusEffect("saved", 2, {"effects": [{"x": [1, 2]}]})},
        scheduled_events=(ScheduledEvent(6, (effect,), "payout"),),
        action_triggers=(
            ActionTrigger("approve", (effect,), when="counters.saved > 0"),
        ),
        encounter_triggers=(EncounterTrigger((effect,), npc_id="npc"),),
        encounter_overrides=(EncounterOverride(probability={"expr": "0.5"}),),
        encounter_modifiers=(EncounterModifier(npc_weights={"npc": 2}),),
        required_action="approve",
        required_action_penalty_effects=(effect,),
    )
    key = state.to_cache_key()  # Populate lazy keys before spawning/exporting.
    payload = serialize_state(state)
    restored = deserialize_state(json.loads(json.dumps(payload)))
    worker = pickle.loads(pickle.dumps(state))
    assert restored.to_cache_key() == key == worker.to_cache_key()
    assert serialize_state(restored) == payload == serialize_state(worker)
    payload["scheduled_events"][0]["effects"][0]["params"]["effects"][0]["params"][
        "amount"
    ]["expr"] = "99"
    assert state.to_cache_key() == key
    assert restored.to_cache_key() == key
    assert isinstance(worker.scheduled_events[0].effects[0].params, FrozenMapping)


def test_frozen_numeric_probability_and_snapshot_payloads_use_existing_semantics(
    data_factory,
):
    data = data_factory()
    state = GameState(1, 10, 3, 3, 0, 0)
    assert resolve_expr(freeze_payload({"expr": "coins + 2"}), state, data) == 12
    assert (
        resolve_probability(
            freeze_payload({"expr": "25", "format": "percent"}), state, data
        )
        == 0.25
    )
    scheduled = EffectSpec(
        "schedule_effects",
        {
            "after_cases": 2,
            "effects": [
                {
                    "type": "add_resource",
                    "params": {
                        "resource": "coins",
                        "amount": {"expr": "coins", "snapshot": True},
                    },
                }
            ],
        },
    )
    result = apply_effects(state, (scheduled,), data, Rng(42))
    assert result.scheduled_events[0].effects[0].params["amount"] == 10
    ended = apply_effects(
        state, (EffectSpec("end_run", {"reason": "saved reason"}),), data
    )
    assert ended.end_reason == "saved reason"


def test_thawed_payload_has_no_shared_mutable_children():
    frozen = freeze_payload({"nested": [{"values": [1, 2]}]})
    output = thaw_payload(frozen)
    output["nested"][0]["values"].append(3)
    assert thaw_payload(frozen) == {"nested": [{"values": [1, 2]}]}
    assert json.loads(json.dumps(thaw_payload(frozen))) == {
        "nested": [{"values": [1, 2]}]
    }


def test_unknown_mutable_leaves_are_not_silently_cached():
    with pytest.raises(TypeError, match="Unsupported mutable payload type"):
        freeze_payload({"value": bytearray(b"mutable")})


def test_programmatic_nested_effect_records_keep_schedule_semantics(data_factory):
    data = data_factory()
    state = GameState(1, 10, 3, 3, 0, 0)
    inner = EffectSpec("add_resource", {"resource": "coins", "amount": 2})
    outer = EffectSpec("schedule_effects", {"after_cases": 2, "effects": [inner]})
    result = apply_effects(state, (outer,), data, Rng(42))
    assert result.scheduled_events[0].effects == (inner,)
    assert (
        deserialize_state(
            json.loads(json.dumps(serialize_state(result)))
        ).to_cache_key()
        == result.to_cache_key()
    )
