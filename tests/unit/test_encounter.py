import pytest

from justice_sim.engine.encounter import UniformEncounterModel, select_encounter
from justice_sim.models.offer import JusticeData
from justice_sim.models.state import EncounterOverride, GameState
from justice_sim.util.validation import build_minimal_data


class FixedRng:
    def __init__(self, value: float):
        self.value = value

    def random(self) -> float:
        return self.value

    def choice(self, seq):
        return seq[0]

    def weighted_choice(self, choices):
        return choices[0][0]


class ChoiceLastRng(FixedRng):
    def choice(self, seq):
        return seq[-1]


@pytest.mark.unit
def test_harbinger_injection_prefers_gratefulbinger_when_roll_is_low():
    data = build_minimal_data()
    state = GameState(
        case_index=5, coins=0, pop=20, mh=3, dismissals=0, retirement_chests=0
    )
    rng = FixedRng(0.0)
    encounter_model = UniformEncounterModel()

    offer_id = select_encounter(state, data, encounter_model, rng)
    assert offer_id == data.special_rules.gratefulbinger.offer_id


@pytest.mark.unit
def test_harbinger_injection_keeps_harbinger_when_roll_is_high():
    data = build_minimal_data()
    state = GameState(
        case_index=5, coins=0, pop=20, mh=3, dismissals=0, retirement_chests=0
    )
    rng = FixedRng(0.9)
    encounter_model = UniformEncounterModel()

    offer_id = select_encounter(state, data, encounter_model, rng)
    assert offer_id == data.special_rules.harbinger.offer_id


@pytest.mark.unit
def test_harbinger_selects_from_pool_when_defined(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"].append(
        {
            "id": "harbinger_offer_alt",
            "npc_id": "the_harbinger",
            "title": "Harbinger Alt",
            "text": "Alt",
            "actions_available": ["approve", "reject"],
            "approve": {"effects": []},
            "reject": {"effects": []},
        }
    )
    data_dict["special_rules"]["harbinger"]["offer_pool"] = [
        "harbinger_offer_alt",
        "harbinger_offer",
    ]
    data = JusticeData.from_dict(data_dict)
    state = GameState(
        case_index=5, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    rng = FixedRng(0.9)
    encounter_model = UniformEncounterModel()
    offer_id = select_encounter(state, data, encounter_model, rng)
    assert offer_id == "harbinger_offer_alt"


@pytest.mark.unit
def test_encounter_override_forces_offer():
    data = build_minimal_data()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
        encounter_overrides=(EncounterOverride(offer_id="offer", remaining_uses=1),),
    )
    rng = FixedRng(0.5)
    encounter_model = UniformEncounterModel()
    offer_id = select_encounter(state, data, encounter_model, rng)
    assert offer_id == "offer"


@pytest.mark.unit
def test_encounter_override_probability_controls_activation(data_dict_factory):
    data = JusticeData.from_dict(data_dict_factory())
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
        encounter_overrides=(
            EncounterOverride(offer_id="offer1", remaining_uses=1, probability=0.2),
        ),
    )
    encounter_model = UniformEncounterModel()

    miss_rng = ChoiceLastRng(0.9)
    offer_id = select_encounter(state, data, encounter_model, miss_rng)
    assert offer_id == "timmy_offer"

    hit_rng = ChoiceLastRng(0.1)
    offer_id = select_encounter(state, data, encounter_model, hit_rng)
    assert offer_id == "offer1"


@pytest.mark.unit
def test_encounter_override_priority_prefers_higher(data_dict_factory):
    data = JusticeData.from_dict(data_dict_factory())
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
        encounter_overrides=(
            EncounterOverride(offer_id="offer1", remaining_uses=1, priority=0),
            EncounterOverride(offer_id="offer2", remaining_uses=1, priority=5),
        ),
    )
    encounter_model = UniformEncounterModel()
    rng = FixedRng(0.5)
    offer_id = select_encounter(state, data, encounter_model, rng)
    assert offer_id == "offer2"
