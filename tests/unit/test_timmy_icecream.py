"""Ice-cream progression from the official client's TimmyIceCream branches."""

import pytest

from justice_sim.engine.encounter import (
    UniformEncounterModel,
    possible_encounter_offers,
)
from justice_sim.engine.reducer import apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.state import GameState
from justice_sim.persistence.runs import deserialize_state, serialize_state

pytestmark = pytest.mark.unit


def icecream_offers(data):
    return [
        next(o for o in data.offers if row in o.client_rows) for row in range(81, 85)
    ]


@pytest.mark.parametrize("stage", range(4))
@pytest.mark.parametrize("action", ["approve", "reject", "dismiss"])
def test_only_approval_advances_icecream(builtin_data, stage, action):
    offers = icecream_offers(builtin_data)
    state = GameState(1, 20, 20, 5, 3, 7, counters={"timmy_icecream_stage": stage})
    result, _ = apply_action(state, offers[stage], action, builtin_data, Rng(0))

    expected_stage = stage + (action == "approve")
    assert result.counters.get("timmy_icecream_stage", 0) == expected_stage
    assert result.counters.get("timmy_rejects", 0) == (action == "reject")
    assert result.case_index == 2
    assert result.dismissals == (2 if action == "dismiss" else 3)
    assert result.mh == (9 if action == "approve" and stage == 3 else 5)
    assert result.coins == (20 - (1, 1, 2, 0)[stage] if action == "approve" else 20)
    if action == "approve":
        assert result.pop == (21 if stage < 3 else 20)
    elif action == "reject":
        assert result.pop == (19 if stage < 3 else 0)
    else:
        assert result.pop == 20

    eligible = possible_encounter_offers(result, builtin_data, UniformEncounterModel())
    assert {o.id for o in offers} & set(eligible) == (
        {offers[expected_stage].id} if expected_stage < 4 else set()
    )


def test_completed_chain_stays_finished_after_save_and_further_cases(builtin_data):
    offers = icecream_offers(builtin_data)
    state = GameState(1, 20, 20, 5, 3, 7)
    model = UniformEncounterModel()
    for offer in offers:
        eligible = possible_encounter_offers(state, builtin_data, model)
        assert {o.id for o in offers} & set(eligible) == {offer.id}
        state, _ = apply_action(state, offer, "approve", builtin_data, Rng(0))

    assert (state.coins, state.pop, state.mh) == (16, 23, 9)
    state = deserialize_state(serialize_state(state))
    assert state.counters["timmy_icecream_stage"] == 4
    harbinger = next(o for o in builtin_data.offers if 5 in o.client_rows)
    state, _ = apply_action(state, harbinger, "reject", builtin_data, Rng(0))
    assert state.case_index == 6
    eligible = possible_encounter_offers(state, builtin_data, model)
    assert not {o.id for o in offers} & set(eligible)
    ordinary_timmy = next(o for o in builtin_data.offers if 0 in o.client_rows)
    assert ordinary_timmy.id in eligible

    # A fresh story has its own counter and starts the chain again.
    fresh = GameState(6, 20, 20, 5, 3, 7)
    assert offers[0].id in possible_encounter_offers(fresh, builtin_data, model)
