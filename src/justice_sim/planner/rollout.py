"""Rollout-based planner implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from math import isfinite, sqrt
import re
from statistics import mean, variance
from typing import Callable


from justice_sim.engine.encounter import (
    EncounterModel,
    UniformEncounterModel,
    consume_forced_encounter,
    select_encounter,
)
from justice_sim.engine.effects import resolve_expr, resolve_probability
from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    apply_action_with_outcome,
    can_afford_action,
    is_action_blocked,
    preview_state_after_encounter_triggers,
)
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import utility, weights_for_preset
from justice_sim.models.offer import (
    BernoulliSpec,
    CategoricalSpec,
    EffectSpec,
    JusticeData,
    OfferSpec,
    OutcomeSpec,
)
from justice_sim.models.state import GameState
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.planner.cache import ValueCache
from justice_sim.util import expr as expr_util


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
    sample_count: int = 0
    utility_samples: tuple[float, ...] = field(default=(), repr=False, compare=False)

    @property
    def confidence_half_width(self) -> float:
        """Return the normal-approximation 95% interval half-width."""
        if self.sample_count <= 1 or self.variance <= 0:
            return 0.0
        return 1.96 * sqrt(self.variance / self.sample_count)


@dataclass(frozen=True)
class PlannerRecommendation:
    best_action: str | None
    action_scores: tuple[ActionScore, ...]


class RolloutPlanner:
    def __init__(
        self,
        data: JusticeData,
        config: PlannerConfig,
        encounter_model: EncounterModel | None = None,
        suggested_rules: SuggestedRules | None = None,
        seed: int | None = None,
    ) -> None:
        self.data = data
        self.config = config
        self.encounter_model = encounter_model or UniformEncounterModel()
        self.rng = Rng(seed)
        self.cache = ValueCache()
        self.weights = weights_for_preset(config.risk_preset)
        self.suggested_rules = suggested_rules or SuggestedRules.empty()
        self._referenced_counters = _referenced_counter_names(
            data, self.suggested_rules
        )

    @classmethod
    def from_defaults(
        cls,
        data: JusticeData,
        suggested_rules: SuggestedRules | None = None,
        seed: int | None = None,
    ) -> "RolloutPlanner":
        defaults = data.defaults.planner_defaults
        config = PlannerConfig(
            horizon_cases=defaults.horizon_cases,
            rollouts_per_action=defaults.rollouts_per_action,
            adaptive_rollouts=defaults.adaptive_rollouts,
            adaptive_rollouts_max=defaults.adaptive_rollouts_max,
            risk_preset=defaults.risk_preset,
        )
        return cls(data, config, suggested_rules=suggested_rules, seed=seed)

    def recommend(
        self,
        state: GameState,
        offer: OfferSpec,
        progress: Callable[[int], None] | None = None,
    ) -> PlannerRecommendation:
        eligible_actions = self._eligible_actions(state, offer)
        if not eligible_actions:
            return PlannerRecommendation(
                best_action=None,
                action_scores=tuple(self._deterministic_action_scores(state, offer)),
            )
        fast_path = self._fast_path_recommendation(
            state, offer, eligible_actions=eligible_actions
        )
        if fast_path is not None:
            return fast_path
        raw_scores = self._score_actions(
            state, offer, self.config.rollouts_per_action, progress=progress
        )
        scores = self._apply_action_biases(state, offer, raw_scores)
        adaptive_actions = self._adaptive_actions(scores, eligible_actions)
        if (
            self.config.adaptive_rollouts
            and self.config.adaptive_rollouts_max > self.config.rollouts_per_action
            and adaptive_actions
        ):
            additional_rollouts = (
                self.config.adaptive_rollouts_max - self.config.rollouts_per_action
            )
            additional_scores = self._score_actions(
                state,
                offer,
                additional_rollouts,
                progress=progress,
                actions=adaptive_actions,
                rollout_start=self.config.rollouts_per_action,
            )
            additions_by_action = {score.action: score for score in additional_scores}
            raw_scores = [
                self._combine_scores(score, additions_by_action[score.action])
                if score.action in additions_by_action
                else score
                for score in raw_scores
            ]
            scores = self._apply_action_biases(
                state,
                offer,
                raw_scores,
            )
        eligible_scores = [
            score for score in scores if score.action in eligible_actions
        ]
        best = max(eligible_scores, key=lambda s: s.expected_utility)
        return PlannerRecommendation(
            best_action=best.action, action_scores=tuple(scores)
        )

    def _fast_path_recommendation(
        self,
        state: GameState,
        offer: OfferSpec,
        *,
        eligible_actions: tuple[str, ...],
    ) -> PlannerRecommendation | None:
        scores = self._deterministic_action_scores(state, offer)
        if not scores:
            return None
        scores = self._apply_action_biases(state, offer, scores)
        if self._is_terminal_offer_state(state, offer):
            eligible_scores = [
                score for score in scores if score.action in eligible_actions
            ]
            best = max(eligible_scores, key=lambda score: score.expected_utility)
            return PlannerRecommendation(
                best_action=best.action, action_scores=tuple(scores)
            )
        upside_action = self._guaranteed_upside_action(
            state, offer, eligible_actions=eligible_actions
        )
        if upside_action is None:
            return None
        return PlannerRecommendation(
            best_action=upside_action, action_scores=tuple(scores)
        )

    def _scores_need_more_samples(
        self, scores: list[ActionScore], eligible_actions: tuple[str, ...]
    ) -> bool:
        return bool(self._adaptive_actions(scores, eligible_actions))

    def _adaptive_actions(
        self, scores: list[ActionScore], eligible_actions: tuple[str, ...]
    ) -> tuple[str, ...]:
        eligible_scores = [
            score
            for score in scores
            if score.action in eligible_actions and isfinite(score.expected_utility)
        ]
        if len(eligible_scores) < 2:
            return ()
        top, second = sorted(
            eligible_scores, key=lambda score: score.expected_utility, reverse=True
        )[:2]
        gap = top.expected_utility - second.expected_utility
        if (
            top.utility_samples
            and len(top.utility_samples) == len(second.utility_samples)
            and len(top.utility_samples) > 1
        ):
            differences = [
                top_value - second_value
                for top_value, second_value in zip(
                    top.utility_samples, second.utility_samples, strict=True
                )
            ]
            standard_error = sqrt(variance(differences) / len(differences))
        else:
            standard_error = sqrt(
                (top.variance / max(top.sample_count, 1))
                + (second.variance / max(second.sample_count, 1))
            )
        uncertainty_threshold = 1.96 * standard_error
        if gap <= max(self.config.epsilon, uncertainty_threshold):
            return (top.action, second.action)
        return ()

    def _combine_scores(self, first: ActionScore, second: ActionScore) -> ActionScore:
        if second.sample_count <= 0:
            return first
        if first.sample_count <= 0:
            return second
        first_count = first.sample_count
        second_count = second.sample_count
        total_count = first_count + second_count
        utility_delta = second.expected_utility - first.expected_utility
        expected_utility = (
            first.expected_utility * first_count
            + second.expected_utility * second_count
        ) / total_count
        expected_chests = (
            first.expected_chests * first_count + second.expected_chests * second_count
        ) / total_count
        death_probability = (
            first.death_probability * first_count
            + second.death_probability * second_count
        ) / total_count
        total_squared_deviation = (
            max(first_count - 1, 0) * first.variance
            + max(second_count - 1, 0) * second.variance
            + utility_delta**2 * first_count * second_count / total_count
        )
        combined_variance = (
            total_squared_deviation / (total_count - 1) if total_count > 1 else 0.0
        )
        return ActionScore(
            action=first.action,
            expected_utility=expected_utility,
            expected_chests=expected_chests,
            death_probability=death_probability,
            variance=combined_variance,
            sample_count=total_count,
            utility_samples=first.utility_samples + second.utility_samples,
        )

    def reset_cache(self) -> None:
        self.cache = ValueCache()

    def _score_actions(
        self,
        state: GameState,
        offer: OfferSpec,
        rollouts: int,
        *,
        progress: Callable[[int], None] | None = None,
        actions: tuple[str, ...] | None = None,
        rollout_start: int = 0,
    ) -> list[ActionScore]:
        scores: list[ActionScore] = []
        selected_actions = actions or offer.actions_available
        action_indexes = {
            action: index for index, action in enumerate(offer.actions_available)
        }
        for action in selected_actions:
            scores.append(
                self._simulate_action(
                    state,
                    offer,
                    action,
                    rollouts,
                    action_indexes[action],
                    progress=progress,
                    rollout_start=rollout_start,
                )
            )
        return scores

    def _simulate_action(
        self,
        state: GameState,
        offer: OfferSpec,
        action: str,
        rollouts: int,
        action_index: int,
        *,
        progress: Callable[[int], None] | None = None,
        rollout_start: int = 0,
    ) -> ActionScore:
        utilities: list[float] = []
        chests: list[float] = []
        deaths = 0
        for rollout_index in range(rollout_start, rollout_start + rollouts):
            rng = self.rng.spawn(rollout_index)
            try:
                next_state, _ = apply_action(state, offer, action, self.data, rng)
            except ActionNotAllowed:
                if progress:
                    progress(1)
                continue
            terminal_state = self._simulate_future(
                next_state, rng, self.config.horizon_cases
            )
            utilities.append(utility(terminal_state, self.data, self.weights))
            chests.append(terminal_state.retirement_chests)
            if terminal_state.ended or terminal_state.mh <= 0:
                deaths += 1
            if progress:
                progress(1)
        if not utilities:
            return ActionScore(
                action=action,
                expected_utility=float("-inf"),
                expected_chests=0.0,
                death_probability=1.0,
                variance=0.0,
                sample_count=0,
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
            sample_count=len(utilities),
            utility_samples=tuple(utilities),
        )

    def _simulate_future(self, state: GameState, rng: Rng, remaining: int) -> GameState:
        current = state
        for _ in range(remaining):
            if current.ended or current.mh <= 0:
                break
            offer_id = select_encounter(current, self.data, self.encounter_model, rng)
            current = consume_forced_encounter(current, offer_id)
            offer = self.data.offers_by_id[offer_id]
            triggered = preview_state_after_encounter_triggers(
                current, offer, self.data, Rng.from_state(rng.state())
            )
            if triggered.ended or triggered.mh <= 0:
                return triggered
            action = self._select_action(current, offer, rng)
            if action is None:
                break
            try:
                current, _ = apply_action(current, offer, action, self.data, rng)
            except ActionNotAllowed:
                break
        return current

    def _select_action(
        self, state: GameState, offer: OfferSpec, rng: Rng
    ) -> str | None:
        actions = self._eligible_actions(state, offer)
        if not actions:
            return None
        best_action = actions[0]
        best_value = float("-inf")
        action_biases = self._biases_for_offer(state, offer)
        policy_rng = rng.spawn(state.case_index)
        for action in actions:
            value = self._expected_action_value(state, offer, action, policy_rng)
            if value is None:
                continue
            value += action_biases.get(action, 0.0)
            if value > best_value:
                best_action = action
                best_value = value
        return best_action

    def _eligible_actions(self, state: GameState, offer: OfferSpec) -> tuple[str, ...]:
        survivable_actions, lethal_actions = self._deterministic_survival_actions(
            state, offer
        )
        base_actions = (
            tuple(
                action
                for action in offer.actions_available
                if action not in lethal_actions
            )
            if survivable_actions
            else offer.actions_available
        )
        constrained_actions = self._apply_action_constraints(state, offer, base_actions)
        possible_actions = tuple(
            action
            for action in constrained_actions
            if self._action_is_possible(state, offer, action)
        )
        possible_base_actions = tuple(
            action
            for action in base_actions
            if self._action_is_possible(state, offer, action)
        )
        return possible_actions or possible_base_actions

    def _guaranteed_upside_action(
        self,
        state: GameState,
        offer: OfferSpec,
        *,
        eligible_actions: tuple[str, ...],
    ) -> str | None:
        profiles: dict[str, tuple[str, tuple]] = {}
        for action in eligible_actions:
            if not self._action_is_possible(state, offer, action):
                continue
            profile = self._action_outcome_profile(state, offer, action)
            if profile is not None:
                profiles[action] = profile
        if len(profiles) < 2:
            return None
        if len({signature for _, signature in profiles.values()}) != 1:
            return None
        positives = [
            action for action, (profile, _) in profiles.items() if profile == "positive"
        ]
        alternatives = [
            profile for profile, _ in profiles.values() if profile != "positive"
        ]
        if (
            len(positives) == 1
            and alternatives
            and all(profile in {"neutral", "negative"} for profile in alternatives)
        ):
            return positives[0]
        return None

    def _action_outcome_profile(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> tuple[str, tuple] | None:
        outcome = self._outcome_for_action(offer, action)
        if outcome is None:
            return None
        scenarios = self._expand_outcome_scenarios(state, outcome)
        if scenarios is None or not scenarios:
            return None

        profiles: list[str] = []
        signatures: set[tuple] = set()
        for scenario_index, (scenario, _probability) in enumerate(scenarios):
            rng = Rng(scenario_index)
            try:
                next_state, _ = apply_action_with_outcome(
                    state, offer, action, scenario, self.data, rng
                )
            except ActionNotAllowed:
                return None
            if rng.state().draws != 0:
                return None
            profiles.append(self._resource_delta_profile(state, next_state))
            signatures.add(self._non_resource_signature(next_state))

        if len(signatures) != 1:
            return None
        if all(profile == profiles[0] for profile in profiles):
            return profiles[0], next(iter(signatures))
        return "mixed", next(iter(signatures))

    def _resource_delta_profile(self, state: GameState, next_state: GameState) -> str:
        deltas = (
            next_state.coins - state.coins,
            next_state.pop - state.pop,
            next_state.mh - state.mh,
            next_state.dismissals - state.dismissals,
            next_state.retirement_chests - state.retirement_chests,
        )
        has_positive = any(value > 1e-9 for value in deltas)
        has_negative = any(value < -1e-9 for value in deltas)
        if has_positive and not has_negative:
            return "positive"
        if has_negative and not has_positive:
            return "negative"
        if not has_positive and not has_negative:
            return "neutral"
        return "mixed"

    def _non_resource_signature(self, state: GameState) -> tuple:
        referenced_counters = getattr(self, "_referenced_counters", None)
        if referenced_counters is None:
            referenced_counters = _referenced_counter_names(
                self.data, self.suggested_rules
            )
            self._referenced_counters = referenced_counters
        relevant_counters = {
            name: value
            for name, value in state.counters.items()
            if name in referenced_counters
        }
        return replace(
            state,
            coins=0,
            pop=0,
            mh=0,
            dismissals=0,
            retirement_chests=0,
            counters=relevant_counters,
        ).to_cache_key()

    def _expected_action_value(
        self, state: GameState, offer: OfferSpec, action: str, rng: Rng
    ) -> float | None:
        outcome = self._outcome_for_action(offer, action)
        if outcome is None:
            return None
        scenarios = self._expand_outcome_scenarios(state, outcome)
        if scenarios is None or not scenarios:
            return self._sample_action_value(state, offer, action, rng)

        expected_value = 0.0
        for scenario_index, (scenario, probability) in enumerate(scenarios):
            scenario_rng = rng.spawn(scenario_index)
            try:
                next_state, _ = apply_action_with_outcome(
                    state,
                    offer,
                    action,
                    scenario,
                    self.data,
                    scenario_rng,
                )
            except ActionNotAllowed:
                return self._sample_action_value(state, offer, action, rng)
            if scenario_rng.state().draws != 0:
                return self._sample_action_value(state, offer, action, rng)
            expected_value += probability * self._cached_utility(next_state)
        return expected_value

    def _sample_action_value(
        self, state: GameState, offer: OfferSpec, action: str, rng: Rng
    ) -> float | None:
        values: list[float] = []
        for sample_index in range(8):
            sample_rng = rng.spawn(sample_index)
            try:
                next_state, _ = apply_action(
                    state, offer, action, self.data, sample_rng
                )
            except ActionNotAllowed:
                return None
            values.append(self._cached_utility(next_state))
        return mean(values)

    def _expand_outcome_scenarios(
        self, state: GameState, outcome: OutcomeSpec
    ) -> list[tuple[OutcomeSpec, float]] | None:
        branch_effects: list[tuple[tuple[EffectSpec, ...], float]]
        if outcome.random is None:
            branch_effects = [((), 1.0)]
        elif isinstance(outcome.random, BernoulliSpec):
            probability = resolve_probability(outcome.random.p, state, self.data)
            probability = min(1.0, max(0.0, probability))
            branch_effects = [
                (tuple(outcome.random.then_effects), probability),
                (tuple(outcome.random.else_effects), 1.0 - probability),
            ]
        elif isinstance(outcome.random, CategoricalSpec):
            total_weight = sum(choice.weight for choice in outcome.random.choices)
            if total_weight <= 0:
                return None
            branch_effects = [
                (tuple(choice.effects), choice.weight / total_weight)
                for choice in outcome.random.choices
            ]
        else:
            return None

        scenarios: list[tuple[OutcomeSpec, float]] = []
        for branch, branch_probability in branch_effects:
            if branch_probability <= 0:
                continue
            expanded = self._expand_effect_scenarios(outcome.effects + branch)
            if expanded is None:
                return None
            scenarios.extend(
                (OutcomeSpec(effects=effects), branch_probability * probability)
                for effects, probability in expanded
            )
        return scenarios

    def _expand_effect_scenarios(
        self, effects: tuple[EffectSpec, ...]
    ) -> list[tuple[tuple[EffectSpec, ...], float]] | None:
        scenarios: list[tuple[tuple[EffectSpec, ...], float]] = [((), 1.0)]
        for effect in effects:
            effect_variants = self._effect_variants(effect)
            if effect_variants is None:
                return None
            next_scenarios: list[tuple[tuple[EffectSpec, ...], float]] = []
            for scenario, scenario_probability in scenarios:
                for variant, variant_probability in effect_variants:
                    next_scenarios.append(
                        (
                            scenario + (variant,),
                            scenario_probability * variant_probability,
                        )
                    )
            scenarios = next_scenarios
        return scenarios

    def _effect_variants(
        self, effect: EffectSpec
    ) -> tuple[tuple[EffectSpec, float], ...] | None:
        if effect.type == "random_range_resource":
            resource = effect.params.get("resource")
            if not resource:
                return None
            try:
                low = int(effect.params.get("min", 0))
                high = int(effect.params.get("max", 0))
            except (TypeError, ValueError):
                return None
            min_amount = min(low, high)
            max_amount = max(low, high)
            probability = 1.0 / (max_amount - min_amount + 1)
            return tuple(
                (
                    EffectSpec(
                        type="add_resource",
                        params={"resource": resource, "amount": amount},
                        when=effect.when,
                        duration_cases=effect.duration_cases,
                        schedule_after_cases=effect.schedule_after_cases,
                        label=effect.label,
                    ),
                    probability,
                )
                for amount in range(min_amount, max_amount + 1)
            )
        if effect.type in {"random_exchange"}:
            return None
        return ((effect, 1.0),)

    def _outcome_for_action(self, offer: OfferSpec, action: str) -> OutcomeSpec | None:
        if action == "approve":
            return offer.approve
        if action == "reject":
            return offer.reject
        if action == "dismiss":
            return offer.dismiss or offer.reject
        return None

    def _deterministic_survival_actions(
        self, state: GameState, offer: OfferSpec
    ) -> tuple[set[str], set[str]]:
        survivable: set[str] = set()
        lethal: set[str] = set()
        for action in offer.actions_available:
            preview = self._action_preview(state, offer, action)
            if preview is None:
                continue
            next_state, draws = preview
            if draws != 0:
                continue
            if next_state.ended or next_state.mh <= 0:
                lethal.add(action)
            else:
                survivable.add(action)
        return survivable, lethal

    def _is_terminal_offer_state(self, state: GameState, offer: OfferSpec) -> bool:
        if state.ended or state.mh <= 0:
            return True
        if not offer.actions_available:
            return True
        for action in offer.actions_available:
            preview = self._action_preview(state, offer, action)
            if preview is None:
                continue
            next_state, draws = preview
            if draws != 0:
                return False
            if not (next_state.ended or next_state.mh <= 0):
                return False
        return True

    def _deterministic_action_scores(
        self, state: GameState, offer: OfferSpec
    ) -> list[ActionScore]:
        scores: list[ActionScore] = []
        for action in offer.actions_available:
            preview = self._action_preview(state, offer, action)
            if preview is None:
                scores.append(
                    ActionScore(
                        action=action,
                        expected_utility=float("-inf"),
                        expected_chests=0.0,
                        death_probability=1.0,
                        variance=0.0,
                    )
                )
                continue
            next_state, _ = preview
            scores.append(
                ActionScore(
                    action=action,
                    expected_utility=utility(next_state, self.data, self.weights),
                    expected_chests=next_state.retirement_chests,
                    death_probability=1.0
                    if (next_state.ended or next_state.mh <= 0)
                    else 0.0,
                    variance=0.0,
                )
            )
        return scores

    def _action_preview(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> tuple[GameState, int] | None:
        rng = Rng(0)
        try:
            next_state, _ = apply_action(state, offer, action, self.data, rng)
        except ActionNotAllowed:
            return None
        return next_state, rng.state().draws

    def _apply_action_biases(
        self,
        state: GameState,
        offer: OfferSpec,
        scores: list[ActionScore],
    ) -> list[ActionScore]:
        if not self.suggested_rules.rules:
            return scores
        biases = self._biases_for_offer(state, offer)
        if not biases:
            return scores
        return [
            replace(
                score,
                expected_utility=score.expected_utility + biases.get(score.action, 0.0),
            )
            for score in scores
        ]

    def _apply_action_constraints(
        self, state: GameState, offer: OfferSpec, actions: tuple[str, ...]
    ) -> tuple[str, ...]:
        constraints = self.suggested_rules.constraints_for_offer(offer.id)
        if not constraints:
            return actions
        ctx = self._bias_context(state)
        forbidden: set[str] = set()
        required: set[str] = set()
        for constraint in constraints:
            if constraint.when and not self._bias_predicate_allows(
                constraint.when, ctx
            ):
                continue
            if constraint.mode == "forbid":
                forbidden.add(constraint.action)
            elif constraint.mode == "require":
                required.add(constraint.action)
        constrained = tuple(action for action in actions if action not in forbidden)
        if required:
            possible_required = tuple(
                action
                for action in constrained
                if action in required and self._action_is_possible(state, offer, action)
            )
            if possible_required:
                return possible_required
        return constrained or actions

    def _action_is_possible(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> bool:
        if action not in offer.actions_available:
            return False
        preview = preview_state_after_encounter_triggers(
            state, offer, self.data, Rng(0)
        )
        if preview.ended:
            return False
        if is_action_blocked(preview, offer, action, self.data):
            return False
        return can_afford_action(preview, offer, action, self.data)

    def _biases_for_offer(self, state: GameState, offer: OfferSpec) -> dict[str, float]:
        biases = self.suggested_rules.biases_for_offer(offer.id)
        if not biases:
            return {}
        ctx = self._bias_context(state)
        totals: dict[str, float] = {}
        for bias in biases:
            if bias.when and not self._bias_predicate_allows(bias.when, ctx):
                continue
            totals[bias.action] = totals.get(bias.action, 0.0) + bias.amount
        return totals

    def _bias_context(self, state: GameState) -> expr_util.ExprContext:
        case_scale_value = resolve_expr(
            {"expr": self.data.special_rules.case_scale.expr}, state, self.data
        )
        harbinger_cost_value = resolve_expr(
            {"expr": self.data.special_rules.harbinger.cost_expr}, state, self.data
        )
        modulus = self.data.special_rules.harbinger.cadence_modulus
        remainder = state.case_index % modulus if modulus > 0 else 0
        harbinger_in = 0 if remainder == 0 else modulus - remainder
        return expr_util.build_predicate_context(
            case_index=state.case_index,
            coins=state.coins,
            pop=state.pop,
            mh=state.mh,
            dismissals=state.dismissals,
            retirement_chests=state.retirement_chests,
            flags=set(state.flags),
            statuses=set(state.statuses.keys()),
            counters=state.counters,
            extra_vars={
                "case_scale": case_scale_value,
                "harbinger_cost": harbinger_cost_value,
                "harbinger_in": harbinger_in,
            },
        )

    def _bias_predicate_allows(
        self, predicate: str, ctx: expr_util.ExprContext
    ) -> bool:
        try:
            return expr_util.evaluate_predicate(predicate, ctx)
        except expr_util.ExprError:
            return False

    def _cached_utility(self, state: GameState) -> float:
        cached = self.cache.get(state, 0)
        if cached is None:
            cached = utility(state, self.data, self.weights)
            self.cache.set(state, 0, cached)
        return cached


_COUNTER_REFERENCE = re.compile(r"\bcounters\.([A-Za-z_][A-Za-z0-9_]*)\b")


def _referenced_counter_names(*roots: object) -> frozenset[str]:
    """Return counters that can affect data- or rule-driven behavior."""
    references: set[str] = set()
    visited: set[int] = set()

    def visit(value: object) -> None:
        if isinstance(value, str):
            references.update(_COUNTER_REFERENCE.findall(value))
            return
        if value is None or isinstance(value, (bool, int, float, bytes)):
            return
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                visit(getattr(value, item.name))
            return
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(key)
                visit(item)
            return
        if isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                visit(item)

    for root in roots:
        visit(root)
    return frozenset(references)
