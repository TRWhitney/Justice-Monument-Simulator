import pytest

from justice_sim.engine.scoring import UtilityWeights, utility
from justice_sim.models.state import GameState


@pytest.mark.unit
def test_utility_rewards_chests_and_penalizes_death(data_factory):
    data = data_factory()
    weights = UtilityWeights(w_chests=10.0, w_death=100.0)
    alive = GameState(
        case_index=1, coins=0, pop=0, mh=1, dismissals=0, retirement_chests=2
    )
    dead = GameState(
        case_index=1, coins=0, pop=0, mh=0, dismissals=0, retirement_chests=2
    )
    assert utility(alive, data, weights) > utility(dead, data, weights)


@pytest.mark.unit
def test_utility_insolvency_penalty_applies(data_factory):
    data = data_factory(cost_expr="5")
    weights = UtilityWeights(w_insolvency=10.0)
    insolvent = GameState(
        case_index=1, coins=0, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    solvent = GameState(
        case_index=1, coins=10, pop=0, mh=2, dismissals=0, retirement_chests=0
    )
    assert utility(solvent, data, weights) > utility(insolvent, data, weights)
