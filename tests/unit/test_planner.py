from pathlib import Path

import pytest

from justice_sim.config import load_data
from justice_sim.models.offer import EffectSpec, JusticeData
from justice_sim.models.state import EncounterTrigger, ForcedEncounter, GameState
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.engine.scoring import UtilityWeights
from justice_sim.engine.rng import Rng
from justice_sim.planner.rollout import ActionScore, PlannerConfig, RolloutPlanner


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
        w_resources=1.0,
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
        w_resources=1.0,
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


@pytest.mark.unit
def test_planner_runs_rollouts_for_required_action(data_dict_factory):
    data_dict = data_dict_factory()
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
        horizon_cases=3,
        rollouts_per_action=200,
        adaptive_rollouts=False,
        adaptive_rollouts_max=200,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=5, pop=3, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]
    progress_calls: list[int] = []

    recommendation = planner.recommend(state, offer, progress=progress_calls.append)

    assert recommendation.best_action == "approve"
    assert progress_calls


@pytest.mark.unit
def test_planner_short_circuits_rollouts_for_strict_upside(data_factory):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=200,
        adaptive_rollouts=False,
        adaptive_rollouts_max=200,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=5, pop=3, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]
    progress_calls: list[int] = []

    recommendation = planner.recommend(state, offer, progress=progress_calls.append)

    assert recommendation.best_action == "approve"
    assert progress_calls == []


@pytest.mark.unit
def test_planner_runs_rollouts_when_only_possible_action_is_strict_upside(
    data_dict_factory,
):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["actions_available"] = ["approve", "reject", "dismiss"]
    data_dict["offers"][0]["approve"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "coins", "amount": 5}}
    ]
    data_dict["offers"][0]["reject"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "mh", "amount": -999}}
    ]
    data_dict["offers"][0]["dismiss"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=200,
        adaptive_rollouts=False,
        adaptive_rollouts_max=200,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    offer = data.offers_by_id["offer1"]
    progress_calls: list[int] = []

    recommendation = planner.recommend(state, offer, progress=progress_calls.append)

    assert recommendation.best_action == "approve"
    assert progress_calls


@pytest.mark.unit
def test_planner_short_circuits_rollouts_for_game_over_outcome(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["actions_available"] = ["approve", "reject"]
    data_dict["offers"][0]["approve"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
    ]
    data_dict["offers"][0]["reject"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
    ]
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=200,
        adaptive_rollouts=False,
        adaptive_rollouts_max=200,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=5, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]
    progress_calls: list[int] = []

    recommendation = planner.recommend(state, offer, progress=progress_calls.append)

    assert progress_calls == []
    assert all(
        score.death_probability == pytest.approx(1.0)
        for score in recommendation.action_scores
    )


@pytest.mark.unit
def test_planner_short_circuits_for_random_sure_thing_upside(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["actions_available"] = ["approve", "reject"]
    data_dict["offers"][0]["approve"] = {
        "effects": [],
        "random": {
            "type": "categorical",
            "choices": [
                {
                    "weight": 1,
                    "effects": [
                        {
                            "type": "random_range_resource",
                            "params": {
                                "resource": "retirement_chests",
                                "min": 2,
                                "max": 3,
                            },
                        }
                    ],
                },
                {
                    "weight": 1,
                    "effects": [
                        {
                            "type": "add_resource",
                            "params": {"resource": "coins", "amount": 1},
                        }
                    ],
                },
            ],
        },
    }
    data_dict["offers"][0]["reject"] = {
        "effects": [
            {"type": "add_resource", "params": {"resource": "coins", "amount": -1}}
        ]
    }
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=200,
        adaptive_rollouts=False,
        adaptive_rollouts_max=200,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=5, pop=3, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]
    progress_calls: list[int] = []

    recommendation = planner.recommend(state, offer, progress=progress_calls.append)

    assert recommendation.best_action == "approve"
    assert progress_calls == []


@pytest.mark.unit
def test_planner_never_recommends_an_unaffordable_action(data_dict_factory):
    data_dict = data_dict_factory()
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject"]
    coin_cost = {
        "type": "add_resource",
        "params": {"resource": "coins", "amount": -10},
    }
    offer_dict["approve"] = {"effects": [coin_cost]}
    offer_dict["reject"] = {"effects": [coin_cost]}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )

    recommendation = planner.recommend(state, data.offers_by_id["offer1"])

    assert recommendation.best_action is None
    assert all(
        score.expected_utility == float("-inf")
        for score in recommendation.action_scores
    )


@pytest.mark.unit
def test_planner_keeps_json_insufficient_funds_exception(data_dict_factory):
    data_dict = data_dict_factory()
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject"]
    offer_dict["allow_insufficient_funds"] = True
    offer_dict["approve"] = {
        "effects": [
            {
                "type": "add_resource",
                "params": {"resource": "coins", "amount": -10},
            },
            {
                "type": "add_resource",
                "params": {"resource": "retirement_chests", "amount": 1},
            },
        ]
    }
    offer_dict["reject"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    progress_calls: list[int] = []

    recommendation = planner.recommend(
        state, data.offers_by_id["offer1"], progress=progress_calls.append
    )

    assert recommendation.best_action == "approve"
    assert progress_calls == []


@pytest.mark.unit
def test_planner_keeps_reject_popularity_exception(data_dict_factory):
    data_dict = data_dict_factory()
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject"]
    offer_dict["approve"] = {"effects": []}
    offer_dict["reject"] = {
        "effects": [
            {
                "type": "add_resource",
                "params": {"resource": "pop", "amount": -10},
            },
            {
                "type": "add_resource",
                "params": {"resource": "coins", "amount": 1},
            },
        ]
    }
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    progress_calls: list[int] = []

    recommendation = planner.recommend(
        state, data.offers_by_id["offer1"], progress=progress_calls.append
    )

    assert recommendation.best_action == "reject"
    assert progress_calls == []


@pytest.mark.unit
def test_planner_does_not_short_circuit_for_mixed_random_action(data_dict_factory):
    data_dict = data_dict_factory()
    data_dict["offers"][0]["actions_available"] = ["approve", "reject"]
    data_dict["offers"][0]["approve"] = {
        "effects": [],
        "random": {
            "type": "bernoulli",
            "p": 0.5,
            "then": [
                {"type": "add_resource", "params": {"resource": "coins", "amount": 2}}
            ],
            "else": [
                {"type": "add_resource", "params": {"resource": "coins", "amount": -2}}
            ],
        },
    }
    data_dict["offers"][0]["reject"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=20,
        adaptive_rollouts=False,
        adaptive_rollouts_max=20,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1, coins=5, pop=3, mh=3, dismissals=0, retirement_chests=0
    )
    offer = data.offers_by_id["offer1"]
    progress_calls: list[int] = []

    planner.recommend(state, offer, progress=progress_calls.append)

    assert progress_calls


@pytest.mark.unit
def test_rollout_stops_immediately_at_zero_mh(data_factory):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data, seed=1)
    dead = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=0,
        dismissals=0,
        retirement_chests=0,
    )

    terminal = planner._simulate_future(dead, Rng(5), remaining=3)

    assert terminal == dead


@pytest.mark.unit
def test_rollout_returns_death_caused_by_encounter_trigger(data_factory):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data, seed=1)
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
        forced_encounters=(ForcedEncounter(1, "offer1"),),
        encounter_triggers=(
            EncounterTrigger(
                offer_id="offer1",
                effects=(
                    EffectSpec(
                        type="add_resource",
                        params={"resource": "mh", "amount": -1},
                    ),
                ),
                remaining_uses=1,
            ),
        ),
    )

    terminal = planner._simulate_future(state, Rng(5), remaining=1)

    assert terminal.mh == 0


@pytest.mark.unit
def test_future_policy_ignores_constraint_when_it_leaves_no_possible_action(
    data_dict_factory,
):
    data_dict = data_dict_factory()
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject", "dismiss"]
    offer_dict["approve"] = {
        "effects": [
            {
                "type": "add_resource",
                "params": {"resource": "coins", "amount": -10},
            }
        ]
    }
    offer_dict["reject"] = {"effects": []}
    offer_dict["dismiss"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    rules = SuggestedRules.from_dict(
        {
            "version": "suggested_rules",
            "rules": [
                {
                    "id": "forbid_only_possible_action",
                    "offer_ids": ["offer1"],
                    "constraints": [{"action": "reject", "mode": "forbid"}],
                }
            ],
        }
    )
    planner = RolloutPlanner.from_defaults(data, suggested_rules=rules)
    state = GameState(
        case_index=1,
        coins=0,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
    )

    action = planner._select_action(state, data.offers_by_id["offer1"], Rng(5))

    assert action == "reject"


@pytest.mark.unit
def test_planner_does_not_force_immediate_upside_when_counter_changes_future(
    data_dict_factory,
):
    data_dict = data_dict_factory(include_grateful=False)
    current = data_dict["offers"][0]
    current["conditions"] = ["case_index == 1"]
    current["actions_available"] = ["approve", "reject"]
    current["approve"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "coins", "amount": 1}}
    ]
    current["reject"]["effects"] = []
    future = data_dict["offers"][1]
    future["id"] = "counter_trap"
    future["npc_id"] = "npc2"
    future["conditions"] = ["case_index >= 2"]
    future["actions_available"] = ["approve", "reject"]
    lethal_effect = {
        "type": "add_resource",
        "when": "counters.npc1_approves >= 1",
        "params": {"resource": "mh", "amount": -10},
    }
    future["approve"] = {"effects": [lethal_effect]}
    future["reject"] = {"effects": [lethal_effect]}
    harbinger = next(
        offer for offer in data_dict["offers"] if offer["id"] == "harbinger_offer"
    )
    data_dict["offers"] = [current, future, harbinger]
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data, seed=2)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=20,
        adaptive_rollouts=False,
        adaptive_rollouts_max=20,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
    )
    progress_calls: list[int] = []

    recommendation = planner.recommend(
        state, data.offers_by_id["offer1"], progress=progress_calls.append
    )

    assert recommendation.best_action == "reject"
    assert progress_calls
    scores = {score.action: score for score in recommendation.action_scores}
    assert scores["approve"].death_probability == pytest.approx(1.0)
    assert scores["reject"].death_probability == pytest.approx(0.0)


@pytest.mark.unit
def test_future_policy_uses_expected_value_for_random_actions(data_dict_factory):
    data_dict = data_dict_factory(include_grateful=False)
    offer = data_dict["offers"][0]
    offer["actions_available"] = ["approve", "reject"]
    offer["approve"] = {
        "effects": [],
        "random": {
            "type": "bernoulli",
            "p": 0.5,
            "then": [
                {"type": "add_resource", "params": {"resource": "coins", "amount": 10}}
            ],
            "else": [
                {"type": "add_resource", "params": {"resource": "coins", "amount": -30}}
            ],
        },
    }
    offer["reject"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data)
    planner.weights = UtilityWeights(
        w_chests=0.0,
        w_death=0.0,
        w_low_mh=0.0,
        w_insolvency=0.0,
        w_resources=1.0,
        w_dismissals=0.0,
        w_progress=0.0,
        mh_threshold=0.0,
    )
    state = GameState(
        case_index=1,
        coins=30,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )

    selected = {
        planner._select_action(state, data.offers_by_id["offer1"], Rng(seed))
        for seed in range(20)
    }

    assert selected == {"reject"}


@pytest.mark.unit
def test_identical_actions_use_common_rollout_streams(data_dict_factory):
    data_dict = data_dict_factory(include_grateful=False)
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject"]
    offer_dict["approve"] = {"effects": []}
    offer_dict["reject"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data, seed=73)
    planner.config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=30,
        adaptive_rollouts=False,
        adaptive_rollouts_max=30,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    offer = data.offers_by_id["offer1"]

    approve = planner._simulate_action(state, offer, "approve", 30, 0)
    reject = planner._simulate_action(state, offer, "reject", 30, 1)

    assert approve.expected_utility == reject.expected_utility
    assert approve.expected_chests == reject.expected_chests
    assert approve.death_probability == reject.death_probability
    assert approve.variance == reject.variance


@pytest.mark.unit
def test_adaptive_sampling_uses_estimator_uncertainty(data_factory):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=200,
        adaptive_rollouts=True,
        adaptive_rollouts_max=1000,
        risk_preset="balanced",
        epsilon=0.05,
    )
    uncertain = [
        ActionScore("approve", 10.0, 0.0, 0.0, 100.0, sample_count=200),
        ActionScore("reject", 9.0, 0.0, 0.0, 100.0, sample_count=200),
    ]
    decisive = [
        ActionScore("approve", 15.0, 0.0, 0.0, 1.0, sample_count=200),
        ActionScore("reject", 9.0, 0.0, 0.0, 1.0, sample_count=200),
    ]

    assert planner._scores_need_more_samples(uncertain, ("approve", "reject"))
    assert not planner._scores_need_more_samples(decisive, ("approve", "reject"))


@pytest.mark.unit
def test_adaptive_sampling_extends_top_actions_without_restarting(data_dict_factory):
    data_dict = data_dict_factory(include_grateful=False)
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject"]
    offer_dict["approve"] = {"effects": []}
    offer_dict["reject"] = {"effects": []}
    data = JusticeData.from_dict(data_dict)
    planner = RolloutPlanner.from_defaults(data, seed=17)
    planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=True,
        adaptive_rollouts_max=9,
        risk_preset="balanced",
    )
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    progress_calls: list[int] = []

    recommendation = planner.recommend(
        state, data.offers_by_id["offer1"], progress=progress_calls.append
    )

    assert len(progress_calls) == 18
    assert {score.sample_count for score in recommendation.action_scores} == {9}
