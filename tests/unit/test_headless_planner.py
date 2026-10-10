from dataclasses import replace
from threading import Event

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


def test_incremental_final_matches_synchronous_across_batches(data_factory):
    data, offer, state, planner = prepared_case(data_factory)
    expected = planner.recommend(state, offer)
    for batch_size in (1, 3, 8, 100):
        updates = list(
            planner.recommend_incremental(state, offer, batch_size=batch_size)
        )
        assert updates[-1].complete and not updates[-1].cancelled
        assert updates[-1].recommendation == expected
        assert [s.utility_samples for s in updates[-1].action_scores] == [
            s.utility_samples for s in expected.action_scores
        ]
        assert len(updates) > 1
        assert any(s.sample_count > 0 for s in updates[0].action_scores)


def test_incremental_cancellation_stops_after_a_batch(data_factory):
    _, offer, state, planner = prepared_case(data_factory)
    stop = Event()
    updates = planner.recommend_incremental(
        state, offer, batch_size=2, cancelled=stop.is_set
    )
    first = next(updates)
    stop.set()
    final = next(updates)
    assert final.cancelled and not final.complete
    assert final.recommendation == first.recommendation
    assert max(s.sample_count for s in final.action_scores) == 2
    assert list(updates) == []


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


@pytest.mark.parametrize("incremental", [False, True])
def test_prepared_eligibility_uses_visible_payment_balance(data_factory, incremental):
    _, offer, state, planner = prepared_case(data_factory)
    offer = replace(
        offer,
        payment_resource="coins",
        approve=OutcomeSpec(
            (EffectSpec("add_resource", {"resource": "coins", "amount": -5}),)
        ),
    )
    state = replace(state, coins=2)
    if incremental:
        result = list(
            planner.recommend_incremental(state, offer, arrival_processed=True)
        )[-1].recommendation
    else:
        result = planner.recommend(state, offer, arrival_processed=True)
    assert result.best_action == "reject"
    assert result.action_scores[0].expected_utility == float("-inf")
    assert planner.recommend(state, offer).action_scores[0].sample_count == 8


def test_prepared_guaranteed_upside_shortcut(data_factory):
    data, offer, state, planner = prepared_case(data_factory)
    offer = replace(
        offer,
        approve=OutcomeSpec(
            (EffectSpec("add_resource", {"resource": "coins", "amount": 1}),)
        ),
    )
    result = planner.recommend(state, offer, arrival_processed=True)
    assert result.best_action == "approve"
    assert all(s.sample_count == 0 for s in result.action_scores)
    assert result.action_scores[0].expected_utility == utility(
        replace(state, case_index=2, coins=15), data, planner.weights
    )
    assert (
        list(planner.recommend_incremental(state, offer, arrival_processed=True))[
            -1
        ].recommendation
        == result
    )


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


def test_prepared_no_eligible_actions_keeps_arrival_skipped(data_factory):
    from justice_sim.models.state import StatusEffect

    _, offer, state, planner = prepared_case(data_factory)
    # Ordinary arrival clears the blocks. A prepared fallback must skip that
    # clearing too, rather than returning finite scores for unavailable actions.
    offer = replace(
        offer,
        arrival_effects=(
            EffectSpec("remove_status", {"status": "cannot_approve"}),
            EffectSpec("remove_status", {"status": "cannot_reject"}),
        ),
    )
    state = replace(
        state,
        statuses={
            "cannot_approve": StatusEffect("cannot_approve", -1),
            "cannot_reject": StatusEffect("cannot_reject", -1),
        },
    )
    result = planner.recommend(state, offer, arrival_processed=True)
    assert result.best_action is None
    assert all(
        s.sample_count == 0 and s.expected_utility == float("-inf")
        for s in result.action_scores
    )
    final = list(planner.recommend_incremental(state, offer, arrival_processed=True))[
        -1
    ]
    assert final.complete and final.recommendation == result


@pytest.mark.parametrize("arrival_processed", [False, True])
def test_incremental_preserves_adaptive_budgets_and_sample_order(
    data_factory, arrival_processed
):
    from justice_sim.models.offer import BernoulliSpec

    _, offer, state, planner = prepared_case(data_factory)
    gamble = OutcomeSpec(
        random=BernoulliSpec(
            "bernoulli",
            0.5,
            (EffectSpec("add_resource", {"resource": "coins", "amount": 3}),),
            (),
        )
    )
    offer = replace(offer, approve=gamble, reject=gamble)
    planner.config = replace(
        planner.config, adaptive_rollouts=True, adaptive_rollouts_max=13
    )
    expected = planner.recommend(state, offer, arrival_processed=arrival_processed)
    assert all(s.sample_count == 13 for s in expected.action_scores)
    for batch_size in (1, 3, 8, 20):
        updates = list(
            planner.recommend_incremental(
                state, offer, batch_size=batch_size, arrival_processed=arrival_processed
            )
        )
        final = updates[-1]
        assert final.complete and final.recommendation == expected
        assert [s.utility_samples for s in final.action_scores] == [
            s.utility_samples for s in expected.action_scores
        ]
        assert all(
            s.sample_count <= 13 for update in updates for s in update.action_scores
        )
        assert all(
            a.sample_count <= b.sample_count
            for previous, current in zip(updates, updates[1:])
            for a, b in zip(previous.action_scores, current.action_scores)
        )


def test_cancellation_before_sampling_and_before_adaptive_topup(data_factory):
    _, offer, state, planner = prepared_case(data_factory)
    planner.config = replace(planner.config, adaptive_rollouts=True)
    stopped = list(planner.recommend_incremental(state, offer, cancelled=lambda: True))
    assert len(stopped) == 1 and stopped[0].cancelled
    assert all(s.sample_count == 0 for s in stopped[0].action_scores)
    event = Event()
    updates = planner.recommend_incremental(
        state, offer, batch_size=8, cancelled=event.is_set
    )
    first = next(updates)
    assert all(s.sample_count == 8 for s in first.action_scores)
    event.set()
    final = next(updates)
    assert final.cancelled and final.recommendation == first.recommendation
    assert list(updates) == []


@pytest.mark.parametrize("batch_size", [0, -1, 1.5, True])
def test_incremental_rejects_invalid_batch_size(data_factory, batch_size):
    _, offer, state, planner = prepared_case(data_factory)
    with pytest.raises(ValueError):
        list(planner.recommend_incremental(state, offer, batch_size=batch_size))


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


def test_incremental_stochastic_future_matches_synchronous(builtin_data):
    from justice_sim.config import load_builtin_suggested_rules

    offer = next(
        o for o in builtin_data.offers if o.title == "Scripticus: Kitchen Loan"
    )
    rules = load_builtin_suggested_rules(builtin_data)
    state = GameState(11, 50, 20, 8, 2, 0)
    planner = RolloutPlanner.from_defaults(builtin_data, rules, seed=42)
    planner.config = replace(
        planner.config,
        horizon_cases=5,
        rollouts_per_action=5,
        adaptive_rollouts=True,
        adaptive_rollouts_max=9,
    )
    expected = planner.recommend(state, offer)
    first_count_estimates = []
    for batch_size in (1, 2, 5):
        updates = list(
            planner.recommend_incremental(state, offer, batch_size=batch_size)
        )
        final = updates[-1]
        assert final.complete and final.recommendation == expected
        assert [s.utility_samples for s in final.action_scores] == [
            s.utility_samples for s in expected.action_scores
        ]
        first_count_estimates.append(updates[0])
    assert all(s.sample_count == 1 for s in first_count_estimates[0].action_scores)


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
