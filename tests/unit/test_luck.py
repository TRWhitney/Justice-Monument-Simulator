from __future__ import annotations

import pytest

from justice_sim.engine.encounter import (
    UniformEncounterModel,
    possible_encounter_offers,
)
from justice_sim.engine.luck import rank_encounter_offer
from justice_sim.engine.rng import RngState
from justice_sim.engine.scoring import weights_for_preset
from justice_sim.models.state import ForcedEncounter, GameState


@pytest.mark.unit
def test_possible_encounter_offers_regular_case(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1, coins=5, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    offers = possible_encounter_offers(state, data, UniformEncounterModel())

    assert set(offers) == {"offer1", "offer2", "timmy_offer"}


@pytest.mark.unit
def test_possible_encounter_offers_harbinger_case(data_factory):
    data = data_factory()
    state = GameState(
        case_index=5, coins=5, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    offers = possible_encounter_offers(state, data, UniformEncounterModel())

    assert set(offers) == {"harbinger_offer", "grateful_offer"}


@pytest.mark.unit
def test_rank_encounter_offer_reflects_rank_and_total(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1, coins=5, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    model = UniformEncounterModel()
    weights = weights_for_preset("balanced")

    best = rank_encounter_offer(
        state,
        "offer2",
        data,
        model,
        weights=weights,
        rng_state=RngState(seed=7, draws=0),
    )
    middle = rank_encounter_offer(
        state,
        "offer1",
        data,
        model,
        weights=weights,
        rng_state=RngState(seed=7, draws=0),
    )
    worst = rank_encounter_offer(
        state,
        "timmy_offer",
        data,
        model,
        weights=weights,
        rng_state=RngState(seed=7, draws=0),
    )

    assert best is not None
    assert middle is not None
    assert worst is not None
    assert best.total == 3
    assert middle.total == 3
    assert worst.total == 3
    assert best.rank < middle.rank < worst.rank


@pytest.mark.unit
def test_rank_encounter_offer_forced_encounter(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
        forced_encounters=(ForcedEncounter(trigger_case_index=1, offer_id="offer1"),),
    )
    model = UniformEncounterModel()
    weights = weights_for_preset("balanced")

    offers = possible_encounter_offers(state, data, model)
    luck = rank_encounter_offer(
        state,
        "offer1",
        data,
        model,
        weights=weights,
        rng_state=RngState(seed=1, draws=0),
    )

    assert offers == ["offer1"]
    assert luck is not None
    assert luck.rank == 1
    assert luck.total == 1
