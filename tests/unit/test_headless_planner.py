from dataclasses import replace

import pytest

from justice_sim.engine.scoring import utility
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import EncounterOverride, EncounterTrigger, GameState
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


def prepared_case(data_factory):
    data = data_factory(include_grateful=False)
    offer = replace(
        data.offers[0],
        approve=OutcomeSpec(),
        reject=OutcomeSpec(),
        actions_available=("approve", "reject"),
    )
    state = GameState(
        1,
        14,
        7,
        3,
        0,
        0,
        encounter_triggers=(
            EncounterTrigger(
                (
                    EffectSpec("add_resource", {"resource": "coins", "amount": 4}),
                    EffectSpec("add_resource", {"resource": "pop", "amount": -3}),
                )
            ),
        ),
        encounter_overrides=(
            EncounterOverride(remaining_uses=2, label="chest_magnetizer"),
        ),
    )
    planner = RolloutPlanner.from_defaults(data, seed=42)
    planner.config = replace(
        planner.config, horizon_cases=0, rollouts_per_action=8, adaptive_rollouts=False
    )
    return data, offer, state, planner


def test_prepared_root_keeps_visible_resources(data_factory):
    data, offer, state, planner = prepared_case(data_factory)
    result = planner.recommend(state, offer, arrival_processed=True)
    expected = utility(replace(state, case_index=2), data, planner.weights)
    assert all(s.expected_utility == expected for s in result.action_scores)
    ordinary = planner.recommend(state, offer)
    expected_ordinary = utility(
        replace(state, case_index=2, coins=18, pop=4), data, planner.weights
    )
    assert all(s.expected_utility == expected_ordinary for s in ordinary.action_scores)
    assert state.encounter_overrides[0].remaining_uses == 2


def test_prepared_root_preserves_override_uses_and_future_arrivals(data_factory):
    from justice_sim.engine.encounter import EncounterModel
    from justice_sim.models.state import ScheduledEvent

    data, offer, state, planner = prepared_case(data_factory)
    quiet = replace(data.offers[1], approve=OutcomeSpec(), reject=OutcomeSpec())
    data = replace(data, offers_by_id={**data.offers_by_id, quiet.id: quiet})
    seen = []

    class RecordingEncounters(EncounterModel):
        def sample_encounter(self, current, data, rng):
            seen.append(current)
            return quiet.id

    planner = RolloutPlanner(
        data,
        replace(planner.config, horizon_cases=2),
        encounter_model=RecordingEncounters(),
        seed=42,
    )
    state = replace(
        state,
        encounter_overrides=(
            EncounterOverride(
                remaining_uses=2, probability=0, label="chest_magnetizer"
            ),
        ),
        scheduled_events=(
            ScheduledEvent(
                4, (EffectSpec("add_resource", {"resource": "coins", "amount": 10}),)
            ),
        ),
    )
    result = planner.recommend(state, offer, arrival_processed=True)
    # Arrival at the root is skipped. Two future arrivals and the due agreement
    # give 14 + 4 + 4 + 10 coins, 7 - 3 - 3 popularity, and case 4.
    expected = utility(GameState(4, 32, 1, 3, 0, 0), data, planner.weights)
    assert all(s.expected_utility == expected for s in result.action_scores)
    assert seen
    assert all(
        s.encounter_overrides[0].remaining_uses == 2 for s in seen if s.case_index == 2
    )
    assert all(
        s.encounter_overrides[0].remaining_uses == 1 for s in seen if s.case_index == 3
    )
    assert state.encounter_overrides[0].remaining_uses == 2


def test_prepared_state_dependent_probability_in_terminal_shortcut(data_factory):
    from justice_sim.models.offer import BernoulliSpec

    _, offer, state, planner = prepared_case(data_factory)
    end = EffectSpec("end_run", {})
    chest = EffectSpec("add_resource", {"resource": "retirement_chests", "amount": 1})
    offer = replace(
        offer,
        approve=OutcomeSpec(
            random=BernoulliSpec("bernoulli", {"expr": "pop/10"}, (chest, end), (end,))
        ),
        reject=OutcomeSpec((end,)),
    )
    result = planner.recommend(state, offer, arrival_processed=True)
    assert result.action_scores[0].expected_chests == pytest.approx(0.7)
    assert all(
        s.sample_count == 0 and s.death_probability == 1 for s in result.action_scores
    )
    assert planner.recommend(state, offer).action_scores[
        0
    ].expected_chests == pytest.approx(0.4)


def test_builtin_ghost_and_hand_agreements_are_not_reapplied(builtin_data):
    from justice_sim.engine.reducer import apply_action
    from justice_sim.engine.rng import Rng

    ghost = next(o for o in builtin_data.offers if o.title == "Ghost: Scare Permit")
    hand = next(
        o for o in builtin_data.offers if o.title == "Reanimated Hand: Above the Law"
    )
    state, _ = apply_action(
        GameState(1, 100, 20, 8, 2, 0), ghost, "approve", builtin_data, Rng(42)
    )
    state, _ = apply_action(state, hand, "approve", builtin_data, Rng(42))
    state = replace(state, coins=14, pop=7)
    visible_hand = replace(
        hand,
        approve=OutcomeSpec(),
        reject=OutcomeSpec(),
        actions_available=("approve", "reject"),
    )
    planner = RolloutPlanner.from_defaults(builtin_data, seed=42)
    planner.config = replace(
        planner.config, horizon_cases=0, rollouts_per_action=2, adaptive_rollouts=False
    )
    prepared = planner.recommend(state, visible_hand, arrival_processed=True)
    ordinary = planner.recommend(state, visible_hand)
    expected = utility(replace(state, case_index=4), builtin_data, planner.weights)
    repeated = utility(
        replace(state, case_index=4, coins=18, pop=4), builtin_data, planner.weights
    )
    assert all(s.expected_utility == expected for s in prepared.action_scores)
    assert all(s.expected_utility == repeated for s in ordinary.action_scores)
    assert all(s.sample_count == 2 for s in prepared.action_scores)


def test_prepared_sample_error_keeps_visible_resources(data_factory):
    from justice_sim.models.state import StatusEffect

    data, offer, state, planner = prepared_case(data_factory)
    state = replace(
        state, statuses={"cannot_approve": StatusEffect("cannot_approve", -1)}
    )
    # Exercise the sampled worker's failure boundary independently of eligibility.
    # Every public sampling path uses this worker with the same root context.
    actual, chests, dead = planner._sample_rollout(
        state,
        offer,
        "approve",
        0,
        encounter_start=replace(state, encounter_overrides=()),
    )
    expected = utility(
        replace(state, ended=True, end_reason="No available simulated action"),
        data,
        planner.weights,
    )
    assert (actual, chests, dead) == (expected, 0, True)
    ordinary, _, _ = planner._sample_rollout(state, offer, "approve", 0)
    repeated = utility(
        replace(
            state,
            coins=18,
            pop=4,
            ended=True,
            end_reason="No available simulated action",
        ),
        data,
        planner.weights,
    )
    assert ordinary == repeated
