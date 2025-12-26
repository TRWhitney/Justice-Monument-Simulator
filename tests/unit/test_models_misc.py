import pytest

from justice_sim.models.actions import ACTIONS
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.outcomes import OutcomeResult
from justice_sim.planner.mcts import MctsPlanner


@pytest.mark.unit
def test_actions_constant_includes_expected_values():
    assert "approve" in ACTIONS
    assert "reject" in ACTIONS
    assert "dismiss" in ACTIONS


@pytest.mark.unit
def test_outcome_result_holds_payload():
    outcome = OutcomeSpec(effects=(EffectSpec(type="noop", params={}),))
    result = OutcomeResult(outcome=outcome, random_label="branch")
    assert result.outcome == outcome
    assert result.random_label == "branch"


@pytest.mark.unit
def test_mcts_planner_not_implemented():
    planner = MctsPlanner()
    with pytest.raises(NotImplementedError):
        planner.recommend(None)
