import pytest

from justice_sim.engine.encounter import UniformEncounterModel, select_encounter
from justice_sim.models.state import GameState
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
