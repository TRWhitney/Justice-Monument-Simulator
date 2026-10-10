"""Optional CPU pacing preserves decision results and remains decision-local."""

from dataclasses import asdict
from threading import Event

import pytest

from justice_sim.models.state import GameState
from justice_sim.headless import PacingConfig
from justice_sim.planner.pacing import CpuPacer
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

pytestmark = pytest.mark.unit


def planner_case(data):
    offer = next(o for o in data.offers if o.title == "Scripticus: Kitchen Loan")
    state = GameState(11, 50, 20, 8, 2, 0)
    planner = RolloutPlanner(
        data,
        PlannerConfig(
            horizon_cases=3,
            rollouts_per_action=2,
            adaptive_rollouts=True,
            adaptive_rollouts_max=4,
        ),
        seed=42,
    )
    return planner, state, offer


def test_opt_in_pacing_preserves_adaptive_sample_results(builtin_data):
    planner, state, offer = planner_case(builtin_data)
    expected = planner.recommend(state, offer)
    actual = planner.recommend(state, offer, pacing=PacingConfig())
    assert asdict(actual) == asdict(expected)
    assert any(s.sample_count == 4 for s in actual.action_scores)


class CpuClock:
    def __init__(self, tick=0.0):
        self.cpu = 0.0
        self.tick = tick
        self.pauses = []

    def __call__(self):
        self.cpu += self.tick
        return self.cpu

    def sleep(self, seconds):
        self.pauses.append(seconds)


def test_pacing_defaults_and_configurable_work_budget():
    assert PacingConfig().pause_ms == 5
    assert PacingConfig().work_ms == 50
    clock = CpuClock()
    pacer = CpuPacer(
        PacingConfig(pause_ms=3, work_ms=20), clock=clock, sleeper=clock.sleep
    )
    with pacer.sampling():
        clock.cpu += 0.019
        pacer.checkpoint()
        assert not clock.pauses
        clock.cpu += 0.002
        pacer.checkpoint()
        assert clock.pauses == [0.003]
        pacer.checkpoint()
        assert clock.pauses == [0.003]


def test_pacing_accumulates_sampling_work_and_excludes_consumer_work():
    clock = CpuClock()
    pacer = CpuPacer(PacingConfig(), clock=clock, sleeper=clock.sleep)
    with pacer.sampling():
        clock.cpu += 0.030
        pacer.checkpoint()
    clock.cpu += 100  # Caller computation while incremental sampling is suspended.
    with pacer.sampling():
        pacer.checkpoint()
        assert not clock.pauses
        clock.cpu += 0.021
        pacer.checkpoint()
        assert clock.pauses == [0.005]


def install_clock(monkeypatch, tick=0.01):
    from justice_sim.planner import pacing

    clock = CpuClock(tick)
    monkeypatch.setattr(pacing.time, "thread_time", clock)
    monkeypatch.setattr(pacing.time, "sleep", clock.sleep)
    return clock


@pytest.mark.parametrize("batch", [1, 3])
@pytest.mark.parametrize("prepared", [False, True])
def test_pacing_preserves_incremental_samples_across_batches(
    builtin_data, monkeypatch, batch, prepared
):
    planner, state, offer = planner_case(builtin_data)
    expected = planner.recommend(state, offer, arrival_processed=prepared)
    clock = install_clock(monkeypatch)
    updates = list(
        planner.recommend_incremental(
            state,
            offer,
            batch_size=batch,
            arrival_processed=prepared,
            pacing=PacingConfig(pause_ms=2),
        )
    )
    assert updates[-1].complete
    assert asdict(updates[-1].recommendation) == asdict(expected)
    assert clock.pauses and set(clock.pauses) == {0.002}


@pytest.mark.parametrize("close", [False, True])
def test_pacing_cancellation_and_close_stop_further_sampling(
    builtin_data, monkeypatch, close
):
    planner, state, offer = planner_case(builtin_data)
    clock = install_clock(monkeypatch)
    stop = Event()
    updates = planner.recommend_incremental(
        state, offer, pacing=PacingConfig(), cancelled=stop.is_set
    )
    first = next(updates)
    assert not first.complete
    assert all(s.sample_count == 1 for s in first.action_scores)
    assert len(clock.pauses) > 1  # Pauses occur inside a batch, not just after it.
    count = len(clock.pauses)
    if close:
        updates.close()
    else:
        stop.set()
        final = next(updates)
        assert final.cancelled and not final.complete
        assert asdict(final.recommendation) == asdict(first.recommendation)
    assert list(updates) == []
    assert len(clock.pauses) == count


def test_disabled_pacing_does_not_read_a_clock_or_sleep(builtin_data, monkeypatch):
    from justice_sim.planner import pacing

    planner, state, offer = planner_case(builtin_data)
    clock = install_clock(monkeypatch)
    expected = planner.recommend(state, offer, pacing=PacingConfig())
    assert clock.pauses

    def unexpected(*args):
        pytest.fail("Disabled pacing must not use the clock or sleeper")

    monkeypatch.setattr(pacing.time, "thread_time", unexpected)
    monkeypatch.setattr(pacing.time, "sleep", unexpected)
    assert asdict(planner.recommend(state, offer)) == asdict(expected)
    assert asdict(
        list(planner.recommend_incremental(state, offer))[-1].recommendation
    ) == asdict(expected)


@pytest.mark.parametrize(
    "value", [0, -1, True, float("nan"), float("inf"), "5", 10**1000]
)
@pytest.mark.parametrize("name", ["pause_ms", "work_ms"])
def test_pacing_intervals_must_be_finite_and_positive(name, value):
    with pytest.raises(ValueError):
        PacingConfig(**{name: value})


@pytest.mark.parametrize("value", [True, False, 5, "5ms"])
def test_pacing_option_requires_a_configuration(builtin_data, value):
    planner, state, offer = planner_case(builtin_data)
    with pytest.raises(ValueError):
        planner.recommend(state, offer, pacing=value)
    with pytest.raises(ValueError):
        list(planner.recommend_incremental(state, offer, pacing=value))


def test_worker_initialization_applies_its_own_pacing(builtin_data, monkeypatch):
    from justice_sim.planner import workers

    planner, state, offer = planner_case(builtin_data)
    expected = planner._sample_rollout(state, offer, "approve", 0)
    clock = install_clock(monkeypatch)
    monkeypatch.setattr(workers, "_decision", None)
    workers._initialize(
        builtin_data,
        planner.config,
        planner.encounter_model,
        planner.suggested_rules,
        42,
        planner.weights,
        state,
        offer,
        None,
        PacingConfig(pause_ms=3),
    )
    assert workers.sample_job(("approve", 0)) == expected
    assert clock.pauses and set(clock.pauses) == {0.003}
