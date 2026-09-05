from dataclasses import replace

import pytest

from justice_sim.engine.reducer import (
    apply_action,
    preview_state_after_encounter_triggers,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import (
    EncounterTrigger,
    ForcedEncounter,
    GameState,
    StatusEffect,
)
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def test_blocked_future_is_terminal_without_changing_input(data_factory):
    data = data_factory()
    state = GameState(
        1,
        5,
        3,
        3,
        0,
        0,
        forced_encounters=(ForcedEncounter(1, "offer1"),),
        statuses={a: StatusEffect(a, -1) for a in ("cannot_approve", "cannot_reject")},
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    result = planner._simulate_future(state, Rng(1), 4)
    assert result.ended and result.case_index == 1
    assert result.end_reason == "No available simulated action"
    assert not state.ended


@pytest.mark.parametrize("seed", [0, 1])
def test_random_arrival_is_resolved_once_before_future_choice(data_factory, seed):
    data = data_factory()
    cost = OutcomeSpec(
        effects=(EffectSpec("add_resource", {"resource": "coins", "amount": -1}),)
    )
    offer = replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=cost,
        reject=OutcomeSpec(),
    )
    data = replace(data, offers_by_id={**data.offers_by_id, offer.id: offer})
    trigger = EncounterTrigger(
        effects=(
            EffectSpec(
                "random_range_resource", {"resource": "coins", "min": -2, "max": 0}
            ),
        )
    )
    state = GameState(
        1,
        1,
        3,
        3,
        0,
        0,
        encounter_triggers=(trigger,),
        forced_encounters=(ForcedEncounter(1, offer.id),),
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    rng = Rng(seed)
    result = planner._simulate_future(state, rng, 1)
    assert not result.ended and result.case_index == 2
    assert rng.state().draws == 1
    assert result.counters.get("npc1_rejects") == 1


def test_prepared_arrival_matches_full_reducer_and_rng(data_factory):
    data = data_factory()
    offer = data.offers[0]
    trigger = EncounterTrigger(
        effects=(
            EffectSpec(
                "random_range_resource", {"resource": "coins", "min": 1, "max": 4}
            ),
            EffectSpec(
                "add_encounter_override",
                {
                    "label": "new_arrival_deal",
                    "offer_id": offer.id,
                    "remaining_uses": 1,
                },
            ),
        )
    )
    state = GameState(1, 5, 3, 3, 0, 0, encounter_triggers=(trigger,))
    full_rng, prepared_rng = Rng(17), Rng(17)
    expected, label = apply_action(state, offer, "approve", data, full_rng)
    arrived = preview_state_after_encounter_triggers(state, offer, data, prepared_rng)
    actual, actual_label = apply_action(
        arrived, offer, "approve", data, prepared_rng, encounter_start=state
    )
    assert (actual, actual_label) == (expected, label)
    assert prepared_rng.state() == full_rng.state()
    assert actual.encounter_overrides[0].remaining_uses == 1


def test_unavailable_random_arrivals_are_counted_in_root_samples(data_factory):
    data = data_factory()
    cost = OutcomeSpec(
        effects=(EffectSpec("add_resource", {"resource": "coins", "amount": -1}),)
    )
    offer = replace(
        data.offers[0],
        actions_available=("approve", "reject"),
        approve=cost,
        reject=cost,
    )
    trigger = EncounterTrigger(
        effects=(
            EffectSpec(
                "random_range_resource", {"resource": "coins", "min": -2, "max": 0}
            ),
        )
    )
    state = GameState(1, 1, 3, 3, 0, 0, encounter_triggers=(trigger,))
    planner = RolloutPlanner(
        data,
        PlannerConfig(horizon_cases=0, rollouts_per_action=32, adaptive_rollouts=False),
        seed=1,
    )
    result = planner.recommend(state, offer)
    assert all(
        s.sample_count == 32 and 0 < s.death_probability < 1
        for s in result.action_scores
    )
