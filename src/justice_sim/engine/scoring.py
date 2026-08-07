"""Utility scoring for planner."""

from __future__ import annotations

from dataclasses import dataclass

from justice_sim.engine.effects import (
    advance_case,
    outcome_additive_resource_cost,
    resolve_expr,
    resolve_probability,
)
from justice_sim.engine.rng import Rng
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
    death_penalty = 1.0 if state.ended or state.mh <= 0 else 0.0
    low_mh_penalty = max(0.0, weights.mh_threshold - state.mh)
    insolvency_penalty = _next_harbinger_risk(state, data)
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


def _next_harbinger_risk(state: GameState, data: JusticeData) -> float:
    """Estimate the unavoidable base-Harbinger risk from known state transitions."""
    if state.ended or state.mh <= 0:
        return 0.0
    modulus = data.special_rules.harbinger.cadence_modulus
    if modulus <= 0:
        return 0.0
    remainder = state.case_index % modulus
    offset = 0 if remainder == 0 else modulus - remainder
    projected = state
    projection_rng = Rng(0)
    for _ in range(offset):
        projected = advance_case(projected, data, projection_rng)
        if projected.ended or projected.mh <= 0:
            return 0.0

    if (
        projected.dismissals > 0
        and "cannot_dismiss_harbinger" not in projected.statuses
    ):
        return 0.0
    base_harbinger = data.offers_by_id.get(data.special_rules.harbinger.offer_id)
    if base_harbinger is None:
        cost = resolve_expr(
            {"expr": data.special_rules.harbinger.cost_expr}, projected, data
        )
    else:
        cost = outcome_additive_resource_cost(
            projected, base_harbinger.approve, "coins", data
        )
    if projected.coins >= cost:
        return 0.0

    grateful_probability = 0.0
    grateful_rule = data.special_rules.gratefulbinger
    if grateful_rule:
        grateful_probability = resolve_probability(
            {
                "expr": grateful_rule.replace_harbinger_probability_expr,
                "format": grateful_rule.format,
            },
            projected,
            data,
        )
    grateful_probability = min(1.0, max(0.0, grateful_probability))
    return 1.0 - grateful_probability
