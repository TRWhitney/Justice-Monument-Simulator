from dataclasses import replace

import pytest

from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import ForcedEncounter, GameState
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


def _investment(data):
    return replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=OutcomeSpec(
            effects=(
                EffectSpec("add_resource", {"resource": "coins", "amount": -2}),
                EffectSpec(
                    "schedule_effects",
                    {
                        "after_cases": 3,
                        "effects": [
                            {
                                "type": "add_resource",
                                "params": {"resource": "coins", "amount": 20},
                            }
                        ],
                    },
                ),
            )
        ),
        reject=OutcomeSpec(),
    )


def test_future_policy_values_a_payout_within_the_remaining_horizon(data_factory):
    data = data_factory(include_grateful=False)
    offer = _investment(data)
    quiet = replace(data.offers[1], approve=OutcomeSpec(), reject=OutcomeSpec())
    data = replace(data, offers_by_id={**data.offers_by_id, quiet.id: quiet})
    state = GameState(
        1,
        5,
        3,
        3,
        0,
        0,
        forced_encounters=(
            ForcedEncounter(2, quiet.id),
            ForcedEncounter(3, quiet.id),
        ),
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    assert planner._select_action(state, offer, Rng(1), remaining=0) == "reject"
    assert planner._select_action(state, offer, Rng(1), remaining=1) == "reject"
    assert planner._select_action(state, offer, Rng(1), remaining=2) == "approve"


def test_future_policy_accounts_for_changed_encounters(data_factory):
    data = data_factory(include_grateful=False)
    reward = replace(
        data.offers[1],
        approve=OutcomeSpec(
            effects=(
                EffectSpec(
                    "add_resource", {"resource": "retirement_chests", "amount": 3}
                ),
            )
        ),
        reject=OutcomeSpec(),
    )
    offer = replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=OutcomeSpec(
            effects=(
                EffectSpec("add_resource", {"resource": "coins", "amount": -2}),
                EffectSpec(
                    "add_encounter_override",
                    {"offer_id": reward.id, "remaining_uses": 1},
                ),
            )
        ),
        reject=OutcomeSpec(),
    )
    quiet = replace(data.offers[3], approve=OutcomeSpec(), reject=OutcomeSpec())
    data = replace(
        data,
        offers=(quiet, reward),
        offers_by_id={**data.offers_by_id, quiet.id: quiet, reward.id: reward},
    )
    # Keep the reward out of the ordinary pool; only the override supplies it.
    from justice_sim.engine.encounter import WeightedEncounterModel

    model = WeightedEncounterModel(offer_weights={reward.id: 0, quiet.id: 1})
    planner = RolloutPlanner(
        data, RolloutPlanner.from_defaults(data).config, encounter_model=model, seed=1
    )
    state = GameState(1, 5, 3, 3, 0, 0)
    assert planner._select_action(state, offer, Rng(1), remaining=0) == "reject"
    assert planner._select_action(state, offer, Rng(1), remaining=1) == "approve"


def test_extra_policy_work_is_bounded_and_does_not_recurse(data_factory, monkeypatch):
    data = data_factory(include_grateful=False)
    offer = _investment(data)
    data = replace(data, offers_by_id={**data.offers_by_id, offer.id: offer})
    state = GameState(
        1,
        100,
        3,
        3,
        0,
        0,
        forced_encounters=(
            ForcedEncounter(2, offer.id),
            ForcedEncounter(3, offer.id),
        ),
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    depths = []
    simulate = planner._simulate_future

    def record(state, rng, remaining, *, improve_policy=True):
        depths.append((remaining, improve_policy))
        return simulate(state, rng, remaining, improve_policy=improve_policy)

    monkeypatch.setattr(planner, "_simulate_future", record)
    planner._select_action(state, offer, Rng(1), remaining=2)
    assert depths == [(2, False)] * 4


def test_simple_resource_choices_use_no_extra_policy_rollouts(
    data_factory, monkeypatch
):
    data = data_factory()
    planner = RolloutPlanner.from_defaults(data, seed=1)

    def unexpected(*args, **kwargs):
        pytest.fail("Simple resource choice should not launch policy rollouts")

    monkeypatch.setattr(planner, "_simulate_future", unexpected)
    assert (
        planner._select_action(
            GameState(1, 5, 3, 3, 0, 0), data.offers[0], Rng(1), remaining=12
        )
        == "approve"
    )
