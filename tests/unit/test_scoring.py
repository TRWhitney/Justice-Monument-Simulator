import pytest

from justice_sim.engine.scoring import UtilityWeights, utility
from justice_sim.models.state import GameState, StatusEffect


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


@pytest.mark.unit
def test_insolvency_penalty_ignores_dismissals_when_harbinger_locked(data_factory):
    data = data_factory(cost_expr="5")
    weights = UtilityWeights(
        w_chests=0.0,
        w_death=0.0,
        w_low_mh=0.0,
        w_insolvency=10.0,
        w_resources=0.0,
        w_dismissals=0.0,
        w_progress=0.0,
    )
    blocked = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=2,
        dismissals=1,
        retirement_chests=0,
        statuses={
            "cannot_dismiss_harbinger": StatusEffect(
                name="cannot_dismiss_harbinger", remaining_cases=-1
            )
        },
    )
    unblocked = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=2,
        dismissals=1,
        retirement_chests=0,
    )
    assert utility(unblocked, data, weights) > utility(blocked, data, weights)
