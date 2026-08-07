import pytest

from justice_sim.engine.encounter import (
    LearnedEncounterModel,
    UniformEncounterModel,
    WeightedEncounterModel,
    consume_forced_encounter,
    select_encounter,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.state import EncounterModifier, ForcedEncounter, GameState


@pytest.mark.unit
def test_weighted_encounter_model_respects_modifiers(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=2,
        dismissals=0,
        retirement_chests=0,
        encounter_modifiers=(
            EncounterModifier(offer_weights={"offer2": 0}, mode="set"),
        ),
    )
    model = WeightedEncounterModel()
    offer_id = model.sample_encounter(state, data, Rng(1))
    assert offer_id == "offer1"


@pytest.mark.unit
def test_learned_encounter_model_updates_counts_and_imports():
    model = LearnedEncounterModel()
    model.update_from_log({"offer_id": "offer1"})
    model.update_from_log({"offer_id": "offer1"})
    model.update_from_log({"offer_id": "offer2"})

    exported = model.export_priors()
    assert exported["offer1"] == 2.0
    assert exported["offer2"] == 1.0

    new_model = LearnedEncounterModel()
    new_model.import_priors(exported)
    assert new_model.counts["offer1"] == 2.0


@pytest.mark.unit
def test_forced_encounter_consumed_when_once(data_factory):
    data = data_factory()
    forced = ForcedEncounter(trigger_case_index=1, offer_id="offer2", once=True)
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=2,
        dismissals=0,
        retirement_chests=0,
        forced_encounters=(forced,),
    )
    offer_id = select_encounter(state, data, UniformEncounterModel(), Rng(2))
    assert offer_id == "offer2"

    new_state = consume_forced_encounter(state, offer_id)
    assert not new_state.forced_encounters
