"""Utility scoring for planner."""

from __future__ import annotations

from dataclasses import dataclass

from justice_sim.engine.effects import resolve_expr
from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState


@dataclass(frozen=True)
class UtilityWeights:
    w_chests: float = 20.0
    w_death: float = 150.0
    w_low_mh: float = 8.0
    w_insolvency: float = 60.0
    w_resources: float = 0.1
    w_dismissals: float = 3.0
    w_progress: float = 0.5
    mh_threshold: float = 2.0


_PRESET_WEIGHTS = {
    "safe": UtilityWeights(
        w_death=220.0,
        w_low_mh=12.0,
        w_insolvency=90.0,
        w_resources=0.05,
        w_dismissals=3.5,
        w_progress=0.8,
    ),
    "balanced": UtilityWeights(),
    "greedy": UtilityWeights(
        w_death=90.0,
        w_low_mh=5.0,
        w_insolvency=30.0,
        w_resources=0.2,
        w_dismissals=2.0,
        w_progress=0.3,
    ),
}


def weights_for_preset(preset: str) -> UtilityWeights:
    return _PRESET_WEIGHTS.get(preset, UtilityWeights())


def utility(state: GameState, data: JusticeData, weights: UtilityWeights) -> float:
    death_penalty = 1.0 if state.mh <= 0 else 0.0
    low_mh_penalty = max(0.0, weights.mh_threshold - state.mh)
    insolvency_penalty = 1.0 if _next_harbinger_unpayable(state, data) else 0.0
    resources_score = state.coins + state.pop

    return (
        weights.w_chests * state.retirement_chests
        - weights.w_death * death_penalty
        - weights.w_low_mh * low_mh_penalty
        - weights.w_insolvency * insolvency_penalty
        + weights.w_resources * resources_score
        + weights.w_dismissals * state.dismissals
        + weights.w_progress * state.case_index
    )


def _next_harbinger_unpayable(state: GameState, data: JusticeData) -> bool:
    if state.dismissals > 0 and "cannot_dismiss_harbinger" not in state.statuses:
        return False
    modulus = data.special_rules.harbinger.cadence_modulus
    remainder = state.case_index % modulus
    offset = 0 if remainder == 0 else modulus - remainder
    next_case = state.case_index + offset
    if state.case_index != next_case:
        temp_state = GameState(
            case_index=next_case,
            coins=state.coins,
            pop=state.pop,
            mh=state.mh,
            dismissals=state.dismissals,
            retirement_chests=state.retirement_chests,
            flags=state.flags,
            statuses=state.statuses,
            scheduled_events=state.scheduled_events,
            encounter_modifiers=state.encounter_modifiers,
            forced_encounters=state.forced_encounters,
            required_action=state.required_action,
            required_action_penalty_effects=state.required_action_penalty_effects,
            counters=state.counters,
            ended=state.ended,
            end_reason=state.end_reason,
        )
    else:
        temp_state = state
    cost = resolve_expr(
        {"expr": data.special_rules.harbinger.cost_expr}, temp_state, data
    )
    return state.coins < cost
