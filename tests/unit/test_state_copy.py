from dataclasses import dataclass, fields, replace
import pickle

import pytest

from justice_sim.engine import effects, encounter, reducer, scoring
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import (
    ActionTrigger,
    EncounterModifier,
    EncounterOverride,
    EncounterTrigger,
    ForcedEncounter,
    GameState,
    ScheduledEvent,
    StatusEffect,
    replace_state,
)
from justice_sim.planner import rollout

pytestmark = pytest.mark.unit


def _state():
    effect = EffectSpec("add_resource", {"resource": "coins", "amount": 2})
    return GameState(
        4,
        20,
        5,
        3,
        2,
        1,
        flags=frozenset({"saved"}),
        statuses={"saved": StatusEffect("saved", 3)},
        scheduled_events=(ScheduledEvent(5, (effect,)),),
        encounter_modifiers=(EncounterModifier(npc_weights={"npc1": 2}),),
        forced_encounters=(ForcedEncounter(5, "offer1"),),
        required_action="approve",
        required_action_penalty_effects=(effect,),
        counters={"saved": 4},
        resource_floors={"mh": 1},
        action_triggers=(ActionTrigger("approve", (effect,)),),
        encounter_triggers=(EncounterTrigger((effect,)),),
        encounter_overrides=(EncounterOverride(offer_id="offer1", remaining_uses=2),),
        end_reason="saved reason",
    )


def test_copy_preserves_every_field_sharing_and_pickle():
    state = _state()
    copied = replace_state(state, coins=30)
    assert copied == replace(state, coins=30)
    assert copied is not state and state.coins == 20
    for field in fields(GameState):
        if field.name != "coins":
            assert getattr(copied, field.name) is getattr(state, field.name)
    assert pickle.loads(pickle.dumps(copied)) == copied
    # Exercise replacement of every field, including clearing prior contracts.
    empty = GameState(8, 9, 10, 11, 12, 13, ended=True)
    changes = {field.name: getattr(empty, field.name) for field in fields(GameState)}
    assert replace_state(state, **changes) == replace(state, **changes) == empty


def test_copy_validates_fields_and_drops_derived_attributes():
    state = _state()
    with pytest.raises(TypeError):
        replace_state(state, misspelled_coins=5)
    object.__setattr__(state, "derived_cache", {"stale": True})
    copied = replace_state(state, coins=30)
    assert copied == replace(state, coins=30)
    assert not hasattr(copied, "derived_cache")


def test_subclass_copy_runs_its_constructor():
    @dataclass(frozen=True)
    class CustomState(GameState):
        doubled_coins: float = 0

        def __post_init__(self):
            object.__setattr__(self, "doubled_coins", self.coins * 2)

    state = CustomState(1, 10, 3, 3, 0, 0)
    copied = replace_state(state, coins=20)
    assert type(copied) is CustomState
    assert copied == replace(state, coins=20)
    assert copied.doubled_coins == 40


def test_all_builtin_transitions_match_general_copy(builtin_data, monkeypatch):
    states = [
        GameState(11, 50, 20, 8, 2, 0),
        GameState(14, 0, 1, 1, 0, 0),
        _state(),
    ]
    modules = (effects, encounter, reducer, scoring, rollout)

    def transitions():
        results = []
        for state in states:
            for offer in builtin_data.offers:
                for action in offer.actions_available:
                    rng = Rng(77)
                    try:
                        result, label = reducer.apply_action(
                            state, offer, action, builtin_data, rng
                        )
                        results.append((result, label, rng.state()))
                    except reducer.ActionNotAllowed as error:
                        results.append((str(error), rng.state()))
        return results

    optimized = transitions()
    for module in modules:
        monkeypatch.setattr(module, "replace_state", replace)
    assert transitions() == optimized
