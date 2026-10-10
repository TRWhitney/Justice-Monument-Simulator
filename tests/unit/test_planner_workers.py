"""Optional CPU sampling preserves the public planner's exact seeded results."""

from dataclasses import replace
import multiprocessing
from threading import Event

import pytest

from justice_sim.engine.encounter import LearnedEncounterModel, WeightedEncounterModel
from justice_sim.models.state import GameState
from justice_sim.headless import PacingConfig
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def worker_case(data):
    offer = next(o for o in data.offers if o.title == "Scripticus: Kitchen Loan")
    state = GameState(11, 50, 20, 8, 2, 0)
    config = PlannerConfig(
        horizon_cases=3,
        rollouts_per_action=2,
        adaptive_rollouts=True,
        adaptive_rollouts_max=4,
    )
    return offer, state, config


@pytest.mark.parametrize(
    "batch,workers,prepared", [(1, 2, False), (3, 3, True), (2, 2, False)]
)
def test_cpu_workers_preserve_samples_and_adaptive_results(
    builtin_data, batch, workers, prepared
):
    offer, state, config = worker_case(builtin_data)
    model = (
        LearnedEncounterModel(counts={offer.id: 3})
        if batch == 2
        else WeightedEncounterModel(npc_weights={"scripticus": 3})
    )
    planner = RolloutPlanner(builtin_data, config, model, seed=42)
    planner.weights = replace(planner.weights, w_chests=25)
    expected = planner.recommend(state, offer, arrival_processed=prepared)
    assert any(
        s.sample_count == config.adaptive_rollouts_max for s in expected.action_scores
    )
    updates = list(
        planner.recommend_incremental(
            state, offer, batch_size=batch, workers=workers, arrival_processed=prepared
        )
    )
    assert updates[-1].complete
    assert updates[-1].recommendation == expected
    assert [s.utility_samples for s in updates[-1].action_scores] == [
        s.utility_samples for s in expected.action_scores
    ]
    progress = []
    actual = planner.recommend(
        state,
        offer,
        workers=workers,
        arrival_processed=prepared,
        progress=progress.append,
    )
    assert actual == expected
    assert [s.utility_samples for s in actual.action_scores] == [
        s.utility_samples for s in expected.action_scores
    ]
    assert sum(progress) == sum(s.sample_count for s in expected.action_scores)


@pytest.mark.parametrize("close", [False, True])
def test_parallel_cancellation_and_close_release_workers(builtin_data, close):
    offer, state, config = worker_case(builtin_data)
    planner = RolloutPlanner(
        builtin_data, replace(config, rollouts_per_action=8), seed=42
    )
    before = {p.pid for p in multiprocessing.active_children()}
    stop = Event()
    updates = planner.recommend_incremental(
        state, offer, workers=2, cancelled=stop.is_set
    )
    first = next(updates)
    assert not first.complete and all(s.sample_count == 1 for s in first.action_scores)
    assert {p.pid for p in multiprocessing.active_children()} - before
    if close:
        updates.close()
    else:
        stop.set()
        final = next(updates)
        assert final.cancelled and final.recommendation == first.recommendation
        assert not ({p.pid for p in multiprocessing.active_children()} - before)
        assert list(updates) == []
    assert not ({p.pid for p in multiprocessing.active_children()} - before)


@pytest.mark.parametrize("workers", [0, -1, True, 1.5])
def test_workers_require_a_positive_integer(builtin_data, workers):
    offer, state, config = worker_case(builtin_data)
    planner = RolloutPlanner(builtin_data, config, seed=42)
    with pytest.raises(ValueError):
        planner.recommend(state, offer, workers=workers)
    with pytest.raises(ValueError):
        list(planner.recommend_incremental(state, offer, workers=workers))


def test_precancelled_and_exact_decisions_do_not_spawn(builtin_data, monkeypatch):
    from justice_sim.planner import workers as worker_module

    def unexpected(*args, **kwargs):
        pytest.fail("This decision needs no CPU workers")

    monkeypatch.setattr(worker_module, "ProcessPoolExecutor", unexpected)
    offer, state, config = worker_case(builtin_data)
    planner = RolloutPlanner(builtin_data, config, seed=42)
    result = list(
        planner.recommend_incremental(state, offer, workers=2, cancelled=lambda: True)
    )
    assert len(result) == 1 and result[0].cancelled
    grateful = next(o for o in builtin_data.offers if o.npc_id == "the_gratefulbinger")
    assert planner.recommend(state, grateful, workers=2).best_action == "approve"


def test_custom_model_dispatch_remains_available_in_one_process(builtin_data):
    from justice_sim.engine.encounter import UniformEncounterModel

    class CustomModel(UniformEncounterModel):
        pass

    offer, state, config = worker_case(builtin_data)
    planner = RolloutPlanner(builtin_data, config, CustomModel(), seed=42)
    assert planner.recommend(state, offer).best_action
    with pytest.raises(ValueError):
        planner.recommend(state, offer, workers=2)


def test_worker_errors_propagate_and_release_processes(builtin_data):
    from justice_sim.models.offer import EffectSpec
    from justice_sim.models.state import ScheduledEvent

    offer, state, config = worker_case(builtin_data)
    state = replace(
        state,
        scheduled_events=(
            ScheduledEvent(
                13,
                (
                    EffectSpec(
                        "add_resource", {"resource": "coins", "amount": "unknown_value"}
                    ),
                ),
            ),
        ),
    )
    planner = RolloutPlanner(builtin_data, config, seed=42)
    before = {p.pid for p in multiprocessing.active_children()}
    with pytest.raises(ValueError):
        list(planner.recommend_incremental(state, offer, workers=2))
    assert not ({p.pid for p in multiprocessing.active_children()} - before)


def test_prepared_workers_keep_arrival_agreements_and_remaining_overrides(builtin_data):
    from justice_sim.models.offer import EffectSpec
    from justice_sim.models.state import EncounterOverride, EncounterTrigger

    offer, state, config = worker_case(builtin_data)
    state = replace(
        state,
        coins=14,
        pop=7,
        encounter_triggers=(
            EncounterTrigger(
                (EffectSpec("add_resource", {"resource": "pop", "amount": -3}),),
                when="case_index % 5 != 0",
                label="ghost_scare_pop",
            ),
            EncounterTrigger(
                (EffectSpec("add_resource", {"resource": "coins", "amount": 4}),),
                label="hand_reward",
            ),
        ),
        encounter_overrides=(
            EncounterOverride(remaining_uses=2, label="chest_magnetizer"),
        ),
    )
    planner = RolloutPlanner(
        builtin_data, replace(config, adaptive_rollouts=False), seed=42
    )
    expected = planner.recommend(state, offer, arrival_processed=True)
    final = list(
        planner.recommend_incremental(state, offer, workers=2, arrival_processed=True)
    )[-1]
    assert final.complete and final.recommendation == expected
    assert [s.utility_samples for s in final.action_scores] == [
        s.utility_samples for s in expected.action_scores
    ]
    assert state.coins == 14 and state.pop == 7
    assert state.encounter_overrides[0].remaining_uses == 2


def test_parallel_progress_callback_failure_releases_workers(builtin_data):
    offer, state, config = worker_case(builtin_data)
    planner = RolloutPlanner(builtin_data, config, seed=42)
    before = {p.pid for p in multiprocessing.active_children()}

    def fail(_):
        raise RuntimeError("consumer stopped")

    with pytest.raises(RuntimeError):
        planner.recommend(state, offer, workers=2, progress=fail)
    assert not ({p.pid for p in multiprocessing.active_children()} - before)


def test_paced_workers_preserve_adaptive_results_and_cancel(builtin_data):
    from dataclasses import asdict

    offer, state, config = worker_case(builtin_data)
    planner = RolloutPlanner(builtin_data, config, seed=42)
    expected = planner.recommend(state, offer, arrival_processed=True)
    pacing = PacingConfig(pause_ms=2, work_ms=1)
    actual = planner.recommend(
        state, offer, workers=2, arrival_processed=True, pacing=pacing
    )
    assert asdict(actual) == asdict(expected)
    before = {p.pid for p in multiprocessing.active_children()}
    stop = Event()
    updates = planner.recommend_incremental(
        state, offer, workers=2, pacing=pacing, cancelled=stop.is_set
    )
    first = next(updates)
    stop.set()
    final = next(updates)
    assert final.cancelled and not final.complete
    assert asdict(final.recommendation) == asdict(first.recommendation)
    assert list(updates) == []
    assert not ({p.pid for p in multiprocessing.active_children()} - before)
