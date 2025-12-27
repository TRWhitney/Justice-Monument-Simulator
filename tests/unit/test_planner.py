from pathlib import Path

import pytest

from justice_sim.config import load_data
from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.engine.scoring import UtilityWeights
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner


@pytest.mark.unit
def test_planner_smoke_returns_recommendation():
    data_path = Path(__file__).parent.parent / "fixtures" / "tiny_data.json"
    data = load_data(data_path)
    planner = RolloutPlanner.from_defaults(data)
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )

    recommendation = planner.recommend(state, data.offers_by_id["offer_1"])

    assert recommendation.best_action in {"approve", "reject"}
    assert recommendation.action_scores


@pytest.mark.unit
def test_planner_prefers_strictly_positive_action(data_factory):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )
    planner.weights = UtilityWeights(
        w_chests=0.0,
        w_death=0.0,
        w_low_mh=0.0,
        w_insolvency=0.0,
        w_resources=-1.0,
        w_dismissals=0.0,
        w_progress=0.0,
        mh_threshold=2.0,
    )
    state = GameState(
        case_index=1, coins=0, pop=1, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]

    recommendation = planner.recommend(state, offer)

    assert recommendation.best_action == "approve"


@pytest.mark.unit
def test_planner_avoids_immediate_death_when_survival_available(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["actions_available"] = ["approve", "reject"]
    data_dict["offers"][0]["approve"]["effects"] = [
        {
            "type": "add_resource",
            "params": {"resource": "retirement_chests", "amount": 1},
        },
        {"type": "add_resource", "params": {"resource": "mh", "amount": -1}},
    ]
    data_dict["offers"][0]["reject"]["effects"] = []
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.weights = UtilityWeights(
        w_chests=1000.0,
        w_death=0.0,
        w_low_mh=0.0,
        w_insolvency=0.0,
        w_resources=0.0,
        w_dismissals=0.0,
        w_progress=0.0,
        mh_threshold=0.0,
    )
    state = GameState(
        case_index=1, coins=0, pop=0, mh=1, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]

    recommendation = planner.recommend(state, offer)

    assert recommendation.best_action == "reject"


@pytest.mark.unit
def test_planner_prefers_strict_positive_over_neutral(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["reject"]["effects"] = []
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )
    planner.weights = UtilityWeights(
        w_chests=0.0,
        w_death=0.0,
        w_low_mh=0.0,
        w_insolvency=0.0,
        w_resources=-1.0,
        w_dismissals=0.0,
        w_progress=0.0,
        mh_threshold=2.0,
    )
    state = GameState(
        case_index=1, coins=0, pop=1, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]

    recommendation = planner.recommend(state, offer)

    assert recommendation.best_action == "approve"


@pytest.mark.unit
def test_planner_applies_suggested_rule_bias(data_factory):
    data = data_factory()
    rules = SuggestedRules.from_dict(
        {
            "version": "suggested_rules",
            "rules": [
                {
                    "id": "bias_offer1",
                    "offer_ids": ["offer1"],
                    "biases": [{"action": "approve", "amount": 100}],
                }
            ],
        }
    )
    planner = RolloutPlanner.from_defaults(data, suggested_rules=rules)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )
    planner.weights = UtilityWeights(
        w_chests=0.0,
        w_death=0.0,
        w_low_mh=0.0,
        w_insolvency=0.0,
        w_resources=-1.0,
        w_dismissals=0.0,
        w_progress=0.0,
        mh_threshold=2.0,
    )
    state = GameState(
        case_index=1, coins=0, pop=1, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]

    recommendation = planner.recommend(state, offer)

    assert recommendation.best_action == "approve"


@pytest.mark.unit
def test_planner_respects_suggested_rule_constraint_forbid(data_factory):
    data = data_factory()
    rules = SuggestedRules.from_dict(
        {
            "version": "suggested_rules",
            "rules": [
                {
                    "id": "forbid_approve",
                    "offer_ids": ["offer1"],
                    "constraints": [{"action": "approve", "mode": "forbid"}],
                }
            ],
        }
    )
    planner = RolloutPlanner.from_defaults(data, suggested_rules=rules)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=0, pop=1, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]

    recommendation = planner.recommend(state, offer)

    assert recommendation.best_action == "reject"


@pytest.mark.unit
def test_planner_respects_suggested_rule_constraint_require(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["actions_available"] = ["approve", "reject"]
    data_dict["offers"][0]["approve"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "coins", "amount": -1}}
    ]
    data_dict["offers"][0]["reject"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "coins", "amount": 1}}
    ]
    data = JusticeData.from_dict(data_dict)
    rules = SuggestedRules.from_dict(
        {
            "version": "suggested_rules",
            "rules": [
                {
                    "id": "require_approve",
                    "offer_ids": ["offer1"],
                    "constraints": [{"action": "approve", "mode": "require"}],
                }
            ],
        }
    )
    planner = RolloutPlanner.from_defaults(data, suggested_rules=rules)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=1, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]

    recommendation = planner.recommend(state, offer)

    assert recommendation.best_action == "approve"
