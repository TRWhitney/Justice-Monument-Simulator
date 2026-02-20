"""Rollout-based planner implementation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean, variance
import time
from typing import Callable


from justice_sim.engine.encounter import (
    EncounterModel,
    UniformEncounterModel,
    consume_forced_encounter,
    select_encounter,
)
from justice_sim.engine.effects import resolve_expr
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
from justice_sim.models.offer import EffectSpec, JusticeData, OfferSpec, OutcomeSpec
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
        policy_action = self._policy_override_action(
            state, offer, eligible_actions=eligible_actions
        )
        fast_path = self._fast_path_recommendation(
            state, offer, eligible_actions=eligible_actions, policy_action=policy_action
        )
        if fast_path is not None:
            return fast_path
        scores = self._score_actions(
            state, offer, self.config.rollouts_per_action, progress=progress
        )
        scores = self._apply_action_biases(state, offer, scores)
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
                    state,
                    offer,
                    self.config.adaptive_rollouts_max,
                    progress=progress,
                )
                scores = self._apply_action_biases(state, offer, scores)
        eligible_scores = [
            score for score in scores if score.action in eligible_actions
        ]
        best = max(eligible_scores or scores, key=lambda s: s.expected_utility)
        best_action = policy_action or best.action
        return PlannerRecommendation(
            best_action=best_action, action_scores=tuple(scores)
        )

    def _fast_path_recommendation(
        self,
        state: GameState,
        offer: OfferSpec,
        *,
        eligible_actions: tuple[str, ...],
        policy_action: str | None,
    ) -> PlannerRecommendation | None:
        scores = self._deterministic_action_scores(state, offer)
        if not scores:
            return None
        scores = self._apply_action_biases(state, offer, scores)
        if self._is_terminal_offer_state(state, offer):
            best = max(scores, key=lambda s: s.expected_utility)
            return PlannerRecommendation(
                best_action=best.action, action_scores=tuple(scores)
            )
        if len(eligible_actions) == 1 and self._action_is_possible(
            state, offer, eligible_actions[0]
        ):
            return PlannerRecommendation(
                best_action=eligible_actions[0], action_scores=tuple(scores)
            )
        if policy_action is not None:
            return PlannerRecommendation(
                best_action=policy_action, action_scores=tuple(scores)
            )
        return None

    def reset_cache(self) -> None:
        self.cache = ValueCache()

    def _score_actions(
        self,
        state: GameState,
        offer: OfferSpec,
        rollouts: int,
        *,
        progress: Callable[[int], None] | None = None,
    ) -> list[ActionScore]:
        scores: list[ActionScore] = []
        for index, action in enumerate(offer.actions_available):
            scores.append(
                self._simulate_action(
                    state, offer, action, rollouts, index, progress=progress
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
    ) -> ActionScore:
        utilities: list[float] = []
        chests: list[float] = []
        deaths = 0
        yield_counter = 0
        for rollout_index in range(rollouts):
            token = action_index * 100000 + rollout_index
            rng = self.rng.spawn(token)
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
            if terminal_state.mh <= 0:
                deaths += 1
            if progress:
                progress(1)
            yield_counter += 1
            if yield_counter % 25 == 0:
                time.sleep(0)
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
        for step in range(remaining):
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
            if step % 5 == 0:
                time.sleep(0)
        return current

    def _select_action(self, state: GameState, offer: OfferSpec, rng: Rng) -> str:
        actions = self._apply_action_constraints(state, offer, offer.actions_available)
        best_action = actions[0]
        best_value = float("-inf")
        action_biases = self._biases_for_offer(state, offer)
        for action_index, action in enumerate(actions):
            token = (action_index + 1) * 100000 + state.case_index
            test_rng = rng.spawn(token)
            try:
                next_state, _ = apply_action(state, offer, action, self.data, test_rng)
            except ActionNotAllowed:
                continue
            value = self._policy_value(next_state, test_rng) + action_biases.get(
                action, 0.0
            )
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
        return self._apply_action_constraints(state, offer, base_actions)

    def _policy_override_action(
        self,
        state: GameState,
        offer: OfferSpec,
        *,
        eligible_actions: tuple[str, ...] | None = None,
    ) -> str | None:
        actions = eligible_actions or offer.actions_available
        results: dict[str, tuple[str, tuple]] = {}
        for action in actions:
            evaluation = self._action_outcome_profile(state, offer, action)
            if evaluation is None:
                continue
            results[action] = evaluation
        if len(results) < 2:
            return None
        signatures = {signature for _, signature in results.values()}
        if len(signatures) > 1:
            return None
        positives = [
            action for action, (profile, _) in results.items() if profile == "positive"
        ]
        neutrals = [
            action for action, (profile, _) in results.items() if profile == "neutral"
        ]
        negatives = [
            action for action, (profile, _) in results.items() if profile == "negative"
        ]
        mixed = [
            action for action, (profile, _) in results.items() if profile == "mixed"
        ]
        if len(positives) == 1 and not mixed and (negatives or neutrals):
            return positives[0]
        return None

    def _action_outcome_profile(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> tuple[str, tuple] | None:
        deterministic = self._deterministic_action_delta(state, offer, action)
        if deterministic is not None:
            delta, signature = deterministic
            return self._delta_profile(delta), signature

        stochastic = self._stochastic_action_delta_profile(state, offer, action)
        if stochastic is None:
            return None
        return stochastic

    def _stochastic_action_delta_profile(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> tuple[str, tuple] | None:
        outcome = self._outcome_for_action(offer, action)
        if outcome is None:
            return None
        scenarios = self._expand_outcome_scenarios(outcome)
        if scenarios is None or not scenarios:
            return None

        profiles: list[str] = []
        signatures: set[tuple] = set()
        for scenario in scenarios:
            rng = Rng(0)
            try:
                next_state, _ = apply_action_with_outcome(
                    state,
                    offer,
                    action,
                    scenario,
                    self.data,
                    rng,
                )
            except ActionNotAllowed:
                return None
            if rng.state().draws != 0:
                return None
            delta = {
                "coins": next_state.coins - state.coins,
                "pop": next_state.pop - state.pop,
                "mh": next_state.mh - state.mh,
                "dismissals": next_state.dismissals - state.dismissals,
                "retirement_chests": (
                    next_state.retirement_chests - state.retirement_chests
                ),
            }
            profiles.append(self._delta_profile(delta))
            cache_key = next_state.to_cache_key()
            signatures.add(cache_key[6:13] + cache_key[14:])

        if len(signatures) != 1:
            return None

        if all(profile == "positive" for profile in profiles):
            profile = "positive"
        elif all(profile == "neutral" for profile in profiles):
            profile = "neutral"
        elif all(profile == "negative" for profile in profiles):
            profile = "negative"
        else:
            profile = "mixed"
        return profile, next(iter(signatures))

    def _expand_outcome_scenarios(
        self, outcome: OutcomeSpec
    ) -> list[OutcomeSpec] | None:
        branch_effects: list[tuple[EffectSpec, ...]]
        if outcome.random is None:
            branch_effects = [()]
        elif hasattr(outcome.random, "then_effects"):
            branch_effects = [
                tuple(outcome.random.then_effects),
                tuple(outcome.random.else_effects),
            ]
        elif hasattr(outcome.random, "choices"):
            branch_effects = [
                tuple(choice.effects) for choice in outcome.random.choices
            ]
        else:
            return None

        scenarios: list[OutcomeSpec] = []
        for branch in branch_effects:
            expanded = self._expand_effect_scenarios(outcome.effects + branch)
            if expanded is None:
                return None
            scenarios.extend(OutcomeSpec(effects=effects) for effects in expanded)
        return scenarios

    def _expand_effect_scenarios(
        self, effects: tuple[EffectSpec, ...]
    ) -> list[tuple[EffectSpec, ...]] | None:
        scenarios: list[tuple[EffectSpec, ...]] = [()]
        for effect in effects:
            effect_variants = self._effect_variants(effect)
            if effect_variants is None:
                return None
            next_scenarios: list[tuple[EffectSpec, ...]] = []
            for scenario in scenarios:
                for variant in effect_variants:
                    next_scenarios.append(scenario + (variant,))
            scenarios = next_scenarios
        return scenarios

    def _effect_variants(self, effect: EffectSpec) -> tuple[EffectSpec, ...] | None:
        if (
            effect.when is not None
            or effect.duration_cases is not None
            or effect.schedule_after_cases is not None
        ):
            return None
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
            variants = [
                EffectSpec(
                    type="add_resource",
                    params={"resource": resource, "amount": min_amount},
                )
            ]
            if max_amount != min_amount:
                variants.append(
                    EffectSpec(
                        type="add_resource",
                        params={"resource": resource, "amount": max_amount},
                    )
                )
            return tuple(variants)
        if effect.type in {"random_exchange"}:
            return None
        return (effect,)

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

    def _deterministic_action_delta(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> tuple[dict[str, float], tuple] | None:
        preview = self._action_preview(state, offer, action)
        if preview is None:
            return None
        next_state, draws = preview
        if draws != 0:
            return None
        delta = {
            "coins": next_state.coins - state.coins,
            "pop": next_state.pop - state.pop,
            "mh": next_state.mh - state.mh,
            "dismissals": next_state.dismissals - state.dismissals,
            "retirement_chests": (
                next_state.retirement_chests - state.retirement_chests
            ),
        }
        cache_key = next_state.to_cache_key()
        signature = cache_key[6:13] + cache_key[14:]
        return delta, signature

    def _delta_profile(self, delta: dict[str, float]) -> str:
        if self._is_strictly_positive(delta):
            return "positive"
        if self._is_neutral(delta):
            return "neutral"
        if self._is_strictly_negative(delta):
            return "negative"
        return "mixed"

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

    def _is_strictly_positive(self, delta: dict[str, float]) -> bool:
        positives = [value for value in delta.values() if value > 1e-9]
        negatives = [value for value in delta.values() if value < -1e-9]
        return bool(positives) and not negatives

    def _is_strictly_negative(self, delta: dict[str, float]) -> bool:
        positives = [value for value in delta.values() if value > 1e-9]
        negatives = [value for value in delta.values() if value < -1e-9]
        return bool(negatives) and not positives

    def _is_neutral(self, delta: dict[str, float]) -> bool:
        positives = [value for value in delta.values() if value > 1e-9]
        negatives = [value for value in delta.values() if value < -1e-9]
        return not positives and not negatives

    def _is_mixed(self, delta: dict[str, float]) -> bool:
        positives = [value for value in delta.values() if value > 1e-9]
        negatives = [value for value in delta.values() if value < -1e-9]
        return bool(positives) and bool(negatives)

    def _policy_value(self, state: GameState, rng: Rng) -> float:
        return self._cached_utility(state) + self._forced_chain_bonus(state, rng)

    def _cached_utility(self, state: GameState) -> float:
        cached = self.cache.get(state, 0)
        if cached is None:
            cached = utility(state, self.data, self.weights)
            self.cache.set(state, 0, cached)
        return cached

    def _forced_chain_bonus(self, state: GameState, rng: Rng) -> float:
        if not state.forced_encounters:
            return 0.0
        bonus = 0.0
        temp = state
        for depth in range(2):
            forced = self._next_forced_encounter(temp)
            if not forced:
                break
            offer = self.data.offers_by_id.get(forced.offer_id)
            if not offer:
                break
            stepped = self._fast_forward_case(temp, forced.trigger_case_index)
            action = self._best_immediate_action(stepped, offer, rng.spawn(depth + 1))
            try:
                next_state, _ = apply_action(stepped, offer, action, self.data, rng)
            except ActionNotAllowed:
                break
            bonus += self._cached_utility(next_state) - self._cached_utility(temp)
            temp = next_state
        return bonus

    def _next_forced_encounter(self, state: GameState):
        upcoming = [
            forced
            for forced in state.forced_encounters
            if forced.trigger_case_index >= state.case_index
        ]
        if not upcoming:
            return None
        return min(upcoming, key=lambda forced: forced.trigger_case_index)

    def _fast_forward_case(self, state: GameState, case_index: int) -> GameState:
        if case_index <= state.case_index:
            return state
        return state.__class__(
            case_index=case_index,
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
            resource_floors=state.resource_floors,
            action_triggers=state.action_triggers,
            encounter_triggers=state.encounter_triggers,
            encounter_overrides=state.encounter_overrides,
            ended=state.ended,
            end_reason=state.end_reason,
        )

    def _best_immediate_action(
        self, state: GameState, offer: OfferSpec, rng: Rng
    ) -> str:
        best_action = offer.actions_available[0]
        best_value = float("-inf")
        for action_index, action in enumerate(offer.actions_available):
            token = (action_index + 1) * 10000 + state.case_index
            test_rng = rng.spawn(token)
            try:
                next_state, _ = apply_action(state, offer, action, self.data, test_rng)
            except ActionNotAllowed:
                continue
            value = self._cached_utility(next_state)
            if value > best_value:
                best_action = action
                best_value = value
        return best_action
