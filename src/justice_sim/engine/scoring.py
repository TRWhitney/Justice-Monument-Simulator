"""Utility scoring for planner."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

from justice_sim.engine.effects import (
    advance_case,
    outcome_additive_resource_cost,
    resolve_expr,
    resolve_probability,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import replace_state, ContractKey, GameState
from justice_sim.util.dependencies import referenced_counter_names


@dataclass(frozen=True)
class UtilityWeights:
    w_chests: float = 20.0
    w_death: float = 150.0
    w_low_mh: float = 8.0
    w_insolvency: float = 30.0
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


def utility(
    state: GameState,
    data: JusticeData,
    weights: UtilityWeights,
    *,
    risk_evaluator: RiskEvaluator | None = None,
) -> float:
    death_penalty = 1.0 if state.ended or state.mh <= 0 else 0.0
    low_mh_penalty = max(0.0, weights.mh_threshold - state.mh)
    insolvency_penalty = _next_harbinger_risk(
        state, data, risk_evaluator=risk_evaluator
    )
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


def _next_harbinger_risk(
    state: GameState, data: JusticeData, *, risk_evaluator: RiskEvaluator | None = None
) -> float:
    """Estimate the unavoidable base-Harbinger risk from known state transitions."""
    if state.ended or state.mh <= 0:
        return 0.0
    modulus = data.special_rules.harbinger.cadence_modulus
    if modulus <= 0:
        return 0.0
    remainder = state.case_index % modulus
    offset = 0 if remainder == 0 else modulus - remainder
    projected = state
    if offset and not (
        state.statuses or state.scheduled_events or state.encounter_modifiers
    ):
        projected = replace_state(state, case_index=state.case_index + offset)
    else:
        projection_rng = Rng(0)
        for _ in range(offset):
            projected = advance_case(projected, data, projection_rng)
            if projected.ended or projected.mh <= 0:
                return 0.0

    if data.special_rules.client_encounters:
        return (
            risk_evaluator.client_risk(projected)
            if risk_evaluator is not None
            else _client_harbinger_risk(projected, data)
        )

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
    if grateful_rule and projected.pop >= grateful_rule.minimum_pop:
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


@lru_cache(maxsize=1024)
def _contract_counters(contract_key: ContractKey) -> frozenset[str]:
    return referenced_counter_names(contract_key)


class RiskEvaluator:
    """Cache projected risk independently of utility weights and action history.

    Every state field is retained except counters unreferenced by both the data
    and the state's own contracts. Native encounter selection also reads the
    Fizarre counter. Instances belong to one planner/data lifetime.
    """

    def __init__(self, data: JusticeData, max_entries: int = 10000) -> None:
        from justice_sim.engine.health import HealthProbeCache

        self.data = data
        self.max_entries = max_entries
        self.counter_names = referenced_counter_names(data) | {"fizarre_drink_approves"}
        self._cache: OrderedDict[tuple, float] = OrderedDict()
        self._health_probes = HealthProbeCache(data, max_entries)

    def client_risk(self, state: GameState) -> float:
        contracts = state.contract_key()
        names = self.counter_names | _contract_counters(contracts)
        key = state.to_cache_key(counter_names=names, contracts=contracts)
        cached = self._cache.get(key)
        if cached is None:
            cached = _client_harbinger_risk(
                state, self.data, health_probe=self._health_probes.can_preserve_health
            )
            if len(self._cache) >= self.max_entries:
                self._cache.popitem(last=False)
            self._cache[key] = cached
        return cached


def _client_harbinger_risk(
    state: GameState,
    data: JusticeData,
    *,
    health_probe: Callable[[GameState, OfferSpec, str], bool] | None = None,
) -> float:
    # Use the actual variant pool: a dismissal cannot save Broke Again, and
    # Busted Bills may be payable in popularity despite having no coins.
    from justice_sim.engine.encounter import (
        UniformEncounterModel,
        client_encounter_probabilities,
    )
    from justice_sim.engine.reducer import ActionNotAllowed, action_preserves_health

    distribution = client_encounter_probabilities(state, data, UniformEncounterModel())
    risk = 0.0
    for key, probability in distribution.items():
        offer = data.offers_by_id[key]
        safe = False
        for action in offer.actions_available:
            try:
                safe = (
                    health_probe(state, offer, action)
                    if health_probe is not None
                    else action_preserves_health(state, offer, action, data)
                )
            except ActionNotAllowed:
                continue
            if safe:
                break
        if not safe:
            risk += probability
    return risk
