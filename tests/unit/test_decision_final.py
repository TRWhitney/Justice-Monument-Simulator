"""Settled actions are available independently of unfinished rollout statistics."""

from dataclasses import asdict, replace
from threading import Event

import pytest

from justice_sim.headless import PacingConfig
from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import EncounterOverride, EncounterTrigger, GameState
from justice_sim.engine.encounter import EncounterModel
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def forced_case(data_factory):
    data = data_factory(include_grateful=False)
    offer = replace(
        data.offers[0],
        payment_resource="coins",
        approve=OutcomeSpec(
            (EffectSpec("add_resource", {"resource": "coins", "amount": -5}),)
        ),
        reject=OutcomeSpec(),
    )
    state = GameState(1, 2, 3, 3, 0, 0)
    planner = RolloutPlanner(
        data,
        PlannerConfig(
            horizon_cases=3,
            rollouts_per_action=4,
            adaptive_rollouts=True,
            adaptive_rollouts_max=8,
        ),
        seed=42,
    )
    return planner, state, offer


def test_forced_action_arrives_without_any_forecast(data_factory):
    planner, state, offer = forced_case(data_factory)
    updates = planner.recommend_incremental(state, offer)
    try:
        first = next(updates)
        assert first.best_action == "reject"
        assert first.decision_final and not first.complete and not first.cancelled
        assert first.action_scores == ()
    finally:
        updates.close()


def test_forced_action_can_close_before_forecast_dispatch(data_factory, monkeypatch):
    from justice_sim.planner import pacing

    planner, state, offer = forced_case(data_factory)

    class UnavailableForecast(EncounterModel):
        def sample_encounter(self, state, data, rng):
            raise RuntimeError("forecast requested")

    planner.encounter_model = UnavailableForecast()

    def unexpected_clock():
        pytest.fail("No sampling CPU should be measured before the decision")

    monkeypatch.setattr(pacing.time, "thread_time", unexpected_clock)
    updates = planner.recommend_incremental(state, offer, pacing=PacingConfig())
    first = next(updates)
    assert first.decision_final and first.action_scores == ()
    updates.close()


@pytest.mark.parametrize("batch", [1, 3, 20])
def test_continued_forced_action_preserves_complete_sampled_results(
    data_factory, batch
):
    planner, state, offer = forced_case(data_factory)
    expected = planner.recommend(state, offer)
    updates = list(planner.recommend_incremental(state, offer, batch_size=batch))
    assert updates[0].action_scores == ()
    assert all(u.decision_final and u.best_action == "reject" for u in updates)
    assert all(not u.complete for u in updates[:-1])
    assert updates[-1].complete and not updates[-1].cancelled
    assert asdict(updates[-1].recommendation) == asdict(expected)
    assert (
        next(s for s in expected.action_scores if s.action == "reject").sample_count
        == 4
    )


def test_prepared_eligibility_settles_action_without_repeating_arrival(data_factory):
    planner, state, offer = forced_case(data_factory)
    state = replace(
        state,
        encounter_triggers=(
            EncounterTrigger(
                (EffectSpec("add_resource", {"resource": "coins", "amount": 4}),)
            ),
        ),
        encounter_overrides=(EncounterOverride(remaining_uses=2, probability=0),),
    )
    expected = planner.recommend(state, offer, arrival_processed=True)
    prepared = list(planner.recommend_incremental(state, offer, arrival_processed=True))
    assert prepared[0].decision_final and prepared[0].best_action == "reject"
    assert prepared[0].action_scores == ()
    assert asdict(prepared[-1].recommendation) == asdict(expected)
    assert state.coins == 2 and state.encounter_overrides[0].remaining_uses == 2
    ordinary = list(planner.recommend_incremental(state, offer))
    assert ordinary[0].complete and ordinary[0].decision_final
    ordinary_approval = next(
        s for s in ordinary[0].action_scores if s.action == "approve"
    )
    prepared_approval = next(
        s for s in prepared[-1].action_scores if s.action == "approve"
    )
    assert ordinary_approval.expected_utility != float("-inf")
    assert prepared_approval.expected_utility == float("-inf")


def test_cancelled_forced_decision_stays_settled_with_no_statistics(data_factory):
    planner, state, offer = forced_case(data_factory)
    stop = Event()
    updates = planner.recommend_incremental(state, offer, cancelled=stop.is_set)
    first = next(updates)
    stop.set()
    final = next(updates)
    assert final.cancelled and not final.complete and final.decision_final
    assert final.recommendation == first.recommendation
    assert final.action_scores == ()
    assert list(updates) == []


def test_cancelled_competing_action_estimates_are_still_provisional(data_factory):
    planner, state, offer = forced_case(data_factory)
    state = replace(state, coins=100, dismissals=1)
    stop = Event()
    updates = planner.recommend_incremental(state, offer, cancelled=stop.is_set)
    first = next(updates)
    assert not first.decision_final and not first.complete
    assert any(s.sample_count > 0 for s in first.action_scores)
    stop.set()
    final = next(updates)
    assert final.cancelled and not final.decision_final
    assert not final.complete and final.recommendation == first.recommendation
    assert list(updates) == []


def test_completed_competing_action_decision_is_final(data_factory):
    planner, state, offer = forced_case(data_factory)
    state = replace(state, coins=100, dismissals=1)
    expected = planner.recommend(state, offer)
    updates = list(planner.recommend_incremental(state, offer))
    assert all(not u.decision_final for u in updates[:-1])
    assert updates[-1].decision_final and updates[-1].complete
    assert asdict(updates[-1].recommendation) == asdict(expected)


def test_precancelled_action_has_no_settled_decision(data_factory):
    planner, state, offer = forced_case(data_factory)
    updates = list(planner.recommend_incremental(state, offer, cancelled=lambda: True))
    assert len(updates) == 1
    assert updates[0].cancelled and not updates[0].decision_final
    assert updates[0].best_action is None


def test_exact_recommendation_is_final_and_complete(data_factory):
    from justice_sim.models.state import StatusEffect

    planner, state, offer = forced_case(data_factory)
    end = EffectSpec("end_run", {})
    terminal = replace(offer, approve=OutcomeSpec((end,)), reject=OutcomeSpec((end,)))
    updates = list(planner.recommend_incremental(state, terminal))
    assert len(updates) == 1
    assert updates[0].decision_final and updates[0].complete
    assert all(s.sample_count == 0 for s in updates[0].action_scores)
    blocked = replace(
        state,
        statuses={
            "cannot_approve": StatusEffect("cannot_approve", -1),
            "cannot_reject": StatusEffect("cannot_reject", -1),
        },
    )
    updates = list(planner.recommend_incremental(blocked, offer))
    assert len(updates) == 1
    assert updates[0].decision_final and updates[0].complete
    assert updates[0].best_action is None


@pytest.mark.parametrize("cancel", [False, True])
def test_forced_decision_stops_before_worker_start(data_factory, monkeypatch, cancel):
    from justice_sim.planner import workers

    planner, state, offer = forced_case(data_factory)

    def unexpected(*args, **kwargs):
        pytest.fail("Workers must not start before a forced decision is emitted")

    monkeypatch.setattr(workers, "ProcessPoolExecutor", unexpected)
    stop = Event()
    updates = planner.recommend_incremental(
        state, offer, workers=2, cancelled=stop.is_set
    )
    first = next(updates)
    assert first.decision_final and not first.complete and first.action_scores == ()
    if cancel:
        stop.set()
        final = next(updates)
        assert final.cancelled and final.decision_final and final.action_scores == ()
        assert list(updates) == []
    else:
        updates.close()


def test_workers_continue_from_forced_decision_with_identical_scores(data_factory):
    planner, state, offer = forced_case(data_factory)
    expected = planner.recommend(state, offer)
    updates = list(planner.recommend_incremental(state, offer, workers=2))
    assert updates[0].decision_final and updates[0].action_scores == ()
    assert updates[-1].complete and updates[-1].decision_final
    assert asdict(updates[-1].recommendation) == asdict(expected)
    progress = []
    actual = planner.recommend(state, offer, workers=2, progress=progress.append)
    assert asdict(actual) == asdict(expected)
    assert sum(progress) == 4
