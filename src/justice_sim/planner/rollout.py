"""Rollout-based planner implementation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, variance


from justice_sim.engine.encounter import (
    EncounterModel,
    UniformEncounterModel,
    consume_forced_encounter,
    select_encounter,
)
from justice_sim.engine.reducer import ActionNotAllowed, apply_action
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import utility, weights_for_preset
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import GameState
from justice_sim.planner.cache import ValueCache


@dataclass(frozen=True)
class PlannerConfig:
    horizon_cases: int = 20
    rollouts_per_action: int = 5000
    adaptive_rollouts: bool = True
    adaptive_rollouts_max: int = 20000
    risk_preset: str = "balanced"
    epsilon: float = 0.05


@dataclass(frozen=True)
class ActionScore:
    action: str
    expected_utility: float
    expected_chests: float
    death_probability: float
    variance: float


@dataclass(frozen=True)
class PlannerRecommendation:
    best_action: str
    action_scores: tuple[ActionScore, ...]


class RolloutPlanner:
    def __init__(
        self,
        data: JusticeData,
        config: PlannerConfig,
        encounter_model: EncounterModel | None = None,
        seed: int | None = None,
    ) -> None:
        self.data = data
        self.config = config
        self.encounter_model = encounter_model or UniformEncounterModel()
        self.rng = Rng(seed)
        self.cache = ValueCache()
        self.weights = weights_for_preset(config.risk_preset)

    @classmethod
    def from_defaults(
        cls, data: JusticeData, seed: int | None = None
    ) -> "RolloutPlanner":
        defaults = data.defaults.planner_defaults
        config = PlannerConfig(
            horizon_cases=defaults.horizon_cases,
            rollouts_per_action=defaults.rollouts_per_action,
            adaptive_rollouts=defaults.adaptive_rollouts,
            adaptive_rollouts_max=defaults.adaptive_rollouts_max,
            risk_preset=defaults.risk_preset,
        )
        return cls(data, config, seed=seed)

    def recommend(self, state: GameState, offer: OfferSpec) -> PlannerRecommendation:
        scores = self._score_actions(state, offer, self.config.rollouts_per_action)
        if self.config.adaptive_rollouts and len(scores) > 1:
            sorted_scores = sorted(
                scores, key=lambda s: s.expected_utility, reverse=True
            )
            top, second = sorted_scores[0], sorted_scores[1]
            if (
                abs(top.expected_utility - second.expected_utility)
                <= self.config.epsilon
            ):
                scores = self._score_actions(
                    state, offer, self.config.adaptive_rollouts_max
                )
        best = max(scores, key=lambda s: s.expected_utility)
        return PlannerRecommendation(
            best_action=best.action, action_scores=tuple(scores)
        )

    def _score_actions(
        self, state: GameState, offer: OfferSpec, rollouts: int
    ) -> list[ActionScore]:
        scores: list[ActionScore] = []
        for index, action in enumerate(offer.actions_available):
            scores.append(self._simulate_action(state, offer, action, rollouts, index))
        return scores

    def _simulate_action(
        self,
        state: GameState,
        offer: OfferSpec,
        action: str,
        rollouts: int,
        action_index: int,
    ) -> ActionScore:
        utilities: list[float] = []
        chests: list[float] = []
        deaths = 0
        for rollout_index in range(rollouts):
            token = action_index * 100000 + rollout_index
            rng = self.rng.spawn(token)
            try:
                next_state, _ = apply_action(state, offer, action, self.data, rng)
            except ActionNotAllowed:
                continue
            terminal_state = self._simulate_future(
                next_state, rng, self.config.horizon_cases
            )
            utilities.append(utility(terminal_state, self.data, self.weights))
            chests.append(terminal_state.retirement_chests)
            if terminal_state.mh <= 0:
                deaths += 1
        if not utilities:
            return ActionScore(
                action=action,
                expected_utility=float("-inf"),
                expected_chests=0.0,
                death_probability=1.0,
                variance=0.0,
            )
        expected_utility = mean(utilities)
        expected_chests = mean(chests)
        death_probability = deaths / len(utilities)
        variance_value = variance(utilities) if len(utilities) > 1 else 0.0
        return ActionScore(
            action=action,
            expected_utility=expected_utility,
            expected_chests=expected_chests,
            death_probability=death_probability,
            variance=variance_value,
        )

    def _simulate_future(self, state: GameState, rng: Rng, remaining: int) -> GameState:
        current = state
        for _ in range(remaining):
            if current.ended:
                break
            offer_id = select_encounter(current, self.data, self.encounter_model, rng)
            current = consume_forced_encounter(current, offer_id)
            offer = self.data.offers_by_id[offer_id]
            action = self._select_action(current, offer, rng)
            try:
                current, _ = apply_action(current, offer, action, self.data, rng)
            except ActionNotAllowed:
                break
        return current

    def _select_action(self, state: GameState, offer: OfferSpec, rng: Rng) -> str:
        best_action = offer.actions_available[0]
        best_value = float("-inf")
        for action_index, action in enumerate(offer.actions_available):
            token = (action_index + 1) * 100000 + state.case_index
            test_rng = rng.spawn(token)
            try:
                next_state, _ = apply_action(state, offer, action, self.data, test_rng)
            except ActionNotAllowed:
                continue
            cached = self.cache.get(next_state, 0)
            if cached is None:
                cached = utility(next_state, self.data, self.weights)
                self.cache.set(next_state, 0, cached)
            if cached > best_value:
                best_action = action
                best_value = cached
        return best_action
