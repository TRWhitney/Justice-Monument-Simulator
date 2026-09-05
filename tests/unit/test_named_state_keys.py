"""Named cache keys preserve comparison semantics without cloned states."""

from dataclasses import fields, replace
import pickle

import pytest

from justice_sim.engine.scoring import RiskEvaluator
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import GameState, ScheduledEvent, StateKey, StatusEffect

pytestmark = pytest.mark.unit


def test_named_key_covers_every_state_field_and_keeps_legacy_tuple():
    assert StateKey._fields == tuple(f.name for f in fields(GameState))
    effect = EffectSpec(
        "add_resource", {"resource": "coins", "amount": 2}, when="pop > 0"
    )
    state = GameState(
        4,
        5,
        6,
        7,
        8,
        9,
        flags=frozenset({"b", "a"}),
        statuses={"block": StatusEffect("block", 2, {"nested": [1, 2]})},
        scheduled_events=(ScheduledEvent(5, (effect,), "payment"),),
        counters={"saved": 3},
        resource_floors={"mh": 1},
    )
    legacy = (
        4,
        5,
        6,
        7,
        8,
        9,
        ("a", "b"),
        (("block", 2, (("nested", (1, 2)),)),),
        (
            (
                5,
                (
                    (
                        "add_resource",
                        (("amount", 2), ("resource", "coins")),
                        "pop > 0",
                        None,
                        None,
                        None,
                    ),
                ),
                "payment",
            ),
        ),
        (),
        (),
        None,
        (),
        (("saved", 3),),
        (("mh", 1),),
        (),
        (),
        (),
        False,
        None,
    )
    key = state.to_cache_key()
    assert key == legacy
    assert hash(key) == hash(legacy)
    assert key.scheduled_events == state.contract_key().scheduled_events
    assert pickle.loads(pickle.dumps(key)) == legacy


def test_filtered_and_non_resource_keys_match_original_state_comparisons():
    state = GameState(
        10,
        20,
        30,
        4,
        2,
        8,
        counters={"saved": 2, "history": 99},
        scheduled_events=(
            ScheduledEvent(11, (EffectSpec("end_run", {}, when="counters.saved > 0"),)),
        ),
    )
    names = frozenset({"saved"})
    relevant = replace(state, counters={"saved": 2})
    assert state.to_cache_key(counter_names=names) == relevant.to_cache_key()
    assert (
        state.non_resource_key(names)
        == replace(
            relevant, coins=0, pop=0, mh=0, dismissals=0, retirement_chests=0
        ).to_cache_key()
    )
    assert state.non_resource_key(names) == replace(
        state, coins=99, counters={"saved": 2, "history": 0}
    ).non_resource_key(names)
    assert state.non_resource_key(names) != replace(
        state, case_index=11
    ).non_resource_key(names)
    assert state.non_resource_key(names) != replace(
        state, counters={"saved": 3}
    ).non_resource_key(names)


def test_risk_builds_contract_key_once(builtin_data, monkeypatch):
    original = GameState.contract_key
    calls = []

    def counted(state):
        calls.append(state)
        return original(state)

    monkeypatch.setattr(GameState, "contract_key", counted)
    evaluator = RiskEvaluator(builtin_data)
    evaluator.client_risk(GameState(15, 50, 20, 8, 2, 0))
    assert len(calls) == 1
