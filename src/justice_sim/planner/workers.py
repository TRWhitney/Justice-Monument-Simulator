"""Spawned, decision-local rollout workers with ordered sample delivery."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import multiprocessing
from typing import TYPE_CHECKING

from justice_sim.engine.encounter import (
    EncounterModel,
    LearnedEncounterModel,
    UniformEncounterModel,
    WeightedEncounterModel,
)
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.engine.scoring import UtilityWeights
from justice_sim.models.state import GameState
from justice_sim.planner.pacing import CpuPacer, PacingConfig

if TYPE_CHECKING:
    from collections.abc import Iterator
    from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner

# Each spawned process owns one immutable decision and its own planner caches.
_decision: (
    tuple[RolloutPlanner, GameState, OfferSpec, GameState | None, CpuPacer | None]
    | None
) = None


def validate_workers(planner: RolloutPlanner, workers: int) -> None:
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be a positive integer")
    if workers > 1:
        from justice_sim.planner.rollout import RolloutPlanner

        if type(planner) is not RolloutPlanner or type(planner.encounter_model) not in {
            UniformEncounterModel,
            WeightedEncounterModel,
            EncounterModel,
            LearnedEncounterModel,
        }:
            raise ValueError(
                "CPU workers require RolloutPlanner and a builtin encounter model; "
                "use workers=1 for custom planners or models"
            )


def _initialize(
    data: JusticeData,
    config: PlannerConfig,
    model: EncounterModel,
    rules: SuggestedRules,
    seed: int,
    weights: UtilityWeights,
    state: GameState,
    offer: OfferSpec,
    encounter_start: GameState | None,
    pacing: PacingConfig | None,
) -> None:
    from justice_sim.planner.rollout import RolloutPlanner

    global _decision
    planner = RolloutPlanner(data, config, model, rules, seed)
    planner.weights = weights
    pacer = CpuPacer(pacing) if pacing is not None else None
    _decision = planner, state, offer, encounter_start, pacer


def sample_job(job: tuple[str, int]) -> tuple[float, float, bool]:
    assert _decision is not None
    planner, state, offer, encounter_start, pacer = _decision
    action, index = job
    return planner._sample_rollout(
        state, offer, action, index, encounter_start=encounter_start, pacer=pacer
    )


@contextmanager
def sampling_executor(
    planner: RolloutPlanner,
    state: GameState,
    offer: OfferSpec,
    encounter_start: GameState | None,
    workers: int,
    pacing: PacingConfig | None = None,
) -> Iterator[ProcessPoolExecutor | None]:
    if workers == 1:
        yield None
        return
    executor = ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_initialize,
        initargs=(
            planner.data,
            planner.config,
            planner.encounter_model,
            planner.suggested_rules,
            planner.rng.seed,
            planner.weights,
            state,
            offer,
            encounter_start,
            pacing,
        ),
    )
    try:
        yield executor
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
