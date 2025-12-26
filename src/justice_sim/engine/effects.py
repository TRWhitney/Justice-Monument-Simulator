"""Effect application and case progression."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Iterable, Mapping

from justice_sim.engine import harbinger as harbinger_rules
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import (
    BernoulliSpec,
    CategoricalSpec,
    EffectSpec,
    JusticeData,
    OutcomeSpec,
)
from justice_sim.models.state import (
    EncounterModifier,
    GameState,
    ScheduledEvent,
    StatusEffect,
)
from justice_sim.util import expr as expr_util

NON_NEGATIVE_RESOURCES = {"coins", "pop", "dismissals", "retirement_chests"}


def apply_outcome(
    state: GameState,
    outcome: OutcomeSpec,
    data: JusticeData,
    rng: Rng | None = None,
) -> tuple[GameState, str | None]:
    new_state = apply_effects(state, outcome.effects, data, rng)
    random_label = None
    if outcome.random:
        new_state, random_label = _apply_random(new_state, outcome.random, data, rng)
    return new_state, random_label


def apply_effects(
    state: GameState,
    effects: Iterable[EffectSpec],
    data: JusticeData,
    rng: Rng | None = None,
) -> GameState:
    rng = rng or Rng(0)
    current = state
    for effect in effects:
        if effect.when and not _predicate_allows(effect.when, current, data):
            continue
        if effect.schedule_after_cases is not None:
            current = _schedule_single_effect(current, effect, data)
            continue
        current = _apply_effect(current, effect, data, rng)
    return current


def advance_case(
    state: GameState, data: JusticeData, rng: Rng | None = None
) -> GameState:
    if state.ended:
        return state
    rng = rng or Rng(0)
    next_case = state.case_index + 1

    statuses: dict[str, StatusEffect] = {}
    for name, status in state.statuses.items():
        if status.remaining_cases < 0:
            statuses[name] = status
            continue
        remaining = status.remaining_cases - 1
        if remaining > 0:
            statuses[name] = replace(status, remaining_cases=remaining)

    modifiers: list[EncounterModifier] = []
    for modifier in state.encounter_modifiers:
        if modifier.remaining_cases is None or modifier.remaining_cases < 0:
            modifiers.append(modifier)
            continue
        remaining = modifier.remaining_cases - 1
        if remaining > 0:
            modifiers.append(replace(modifier, remaining_cases=remaining))

    pending_events = []
    triggered_events = []
    for event in state.scheduled_events:
        if event.trigger_case_index == next_case:
            triggered_events.append(event)
        else:
            pending_events.append(event)

    advanced = replace(
        state,
        case_index=next_case,
        statuses=statuses,
        encounter_modifiers=tuple(modifiers),
        scheduled_events=tuple(pending_events),
    )

    for event in triggered_events:
        advanced = apply_effects(advanced, event.effects, data, rng)
    return advanced


def _apply_random(
    state: GameState,
    random_spec: BernoulliSpec | CategoricalSpec,
    data: JusticeData,
    rng: Rng | None,
) -> tuple[GameState, str | None]:
    rng = rng or Rng(0)
    if isinstance(random_spec, BernoulliSpec):
        probability = resolve_probability(random_spec.p, state, data)
        if rng.random() <= probability:
            return apply_effects(state, random_spec.then_effects, data, rng), "then"
        return apply_effects(state, random_spec.else_effects, data, rng), "else"

    choices = []
    for choice in random_spec.choices:
        choices.append((choice, choice.weight))
    chosen = rng.weighted_choice(choices)
    return apply_effects(state, chosen.effects, data, rng), chosen.label


def _predicate_allows(predicate: Any, state: GameState, data: JusticeData) -> bool:
    if isinstance(predicate, str):
        ctx = expr_util.build_predicate_context(
            case_index=state.case_index,
            coins=state.coins,
            pop=state.pop,
            mh=state.mh,
            dismissals=state.dismissals,
            retirement_chests=state.retirement_chests,
            flags=set(state.flags),
            statuses=set(state.statuses.keys()),
            counters=state.counters,
        )
        return expr_util.evaluate_predicate(predicate, ctx)
    return True


def _schedule_single_effect(
    state: GameState, effect: EffectSpec, data: JusticeData
) -> GameState:
    trigger_case = state.case_index + int(effect.schedule_after_cases or 0)
    stripped = EffectSpec(
        type=effect.type,
        params=effect.params,
        when=effect.when,
        duration_cases=effect.duration_cases,
        schedule_after_cases=None,
        label=effect.label,
    )
    event = ScheduledEvent(
        trigger_case_index=trigger_case, effects=(stripped,), label=effect.label
    )
    return replace(state, scheduled_events=state.scheduled_events + (event,))


def _apply_effect(
    state: GameState, effect: EffectSpec, data: JusticeData, rng: Rng
) -> GameState:
    effect_type = effect.type
    params = effect.params

    if effect_type == "add_resource":
        resource = params.get("resource")
        amount = resolve_expr(params.get("amount"), state, data)
        return _update_resource(state, resource, state_delta=amount, data=data)

    if effect_type == "set_resource":
        resource = params.get("resource")
        value = resolve_expr(params.get("value"), state, data)
        return _set_resource(state, resource, value, data)

    if effect_type == "clamp_resource":
        resource = params.get("resource")
        min_value = params.get("min")
        max_value = params.get("max")
        current = getattr(state, resource)
        if min_value is not None:
            current = max(current, resolve_expr(min_value, state, data))
        if max_value is not None:
            current = min(current, resolve_expr(max_value, state, data))
        return _set_resource(state, resource, current, data)

    if effect_type == "multiply_resource":
        resource = params.get("resource")
        factor = resolve_expr(params.get("factor"), state, data)
        return _set_resource(state, resource, getattr(state, resource) * factor, data)

    if effect_type == "add_flag":
        flag = str(params.get("flag"))
        flags = set(state.flags)
        flags.add(flag)
        return replace(state, flags=frozenset(flags))

    if effect_type == "remove_flag":
        flag = str(params.get("flag"))
        flags = set(state.flags)
        flags.discard(flag)
        return replace(state, flags=frozenset(flags))

    if effect_type == "add_status":
        status_name = str(params.get("status"))
        duration = effect.duration_cases if effect.duration_cases is not None else -1
        statuses = dict(state.statuses)
        statuses[status_name] = StatusEffect(
            name=status_name,
            remaining_cases=int(duration),
            data=params.get("data", {}),
        )
        return replace(state, statuses=statuses)

    if effect_type == "remove_status":
        status_name = str(params.get("status"))
        statuses = dict(state.statuses)
        statuses.pop(status_name, None)
        return replace(state, statuses=statuses)

    if effect_type == "schedule_effects":
        after_cases = int(params.get("after_cases", 0))
        raw_effects = params.get("effects", [])
        effects = tuple(_coerce_effect_spec(effect) for effect in raw_effects)
        event = ScheduledEvent(
            trigger_case_index=state.case_index + after_cases,
            effects=effects,
        )
        return replace(state, scheduled_events=state.scheduled_events + (event,))

    if effect_type == "require_next_action":
        action = str(params.get("action"))
        penalty_effects = tuple(
            _coerce_effect_spec(effect) for effect in params.get("penalty_effects", [])
        )
        return replace(
            state,
            required_action=action,
            required_action_penalty_effects=penalty_effects,
        )

    if effect_type == "modify_encounter_weights":
        modifier = EncounterModifier(
            npc_weights=params.get("npc_weights"),
            offer_weights=params.get("offer_weights"),
            mode=params.get("mode", "multiply"),
            remaining_cases=effect.duration_cases,
        )
        return replace(
            state, encounter_modifiers=state.encounter_modifiers + (modifier,)
        )

    if effect_type == "end_run":
        reason = params.get("reason") if isinstance(params, dict) else None
        return replace(state, ended=True, end_reason=reason)

    if effect_type == "random_range_resource":
        resource = params.get("resource")
        min_value = int(params.get("min", 0))
        max_value = int(params.get("max", 0))
        amount = rng.randint(min_value, max_value)
        return _update_resource(state, resource, state_delta=amount, data=data)

    if effect_type in {"noop", "raw_effect"}:
        return state

    return state


def _coerce_effect_spec(effect: EffectSpec | Mapping[str, Any]) -> EffectSpec:
    if isinstance(effect, EffectSpec):
        return effect
    return EffectSpec(
        type=str(effect.get("type")),
        params=dict(effect.get("params", {})),
        when=effect.get("when"),
        duration_cases=effect.get("duration_cases"),
        schedule_after_cases=effect.get("schedule_after_cases"),
        label=effect.get("label"),
    )


def _update_resource(
    state: GameState, resource: str, state_delta: float, data: JusticeData
) -> GameState:
    value = getattr(state, resource)
    new_value = value + state_delta
    if (
        resource in NON_NEGATIVE_RESOURCES
        and data.defaults.debt_mode == "clamp_to_zero"
        and new_value < 0
    ):
        new_value = 0
    return replace(state, **{resource: new_value})


def _set_resource(
    state: GameState, resource: str, value: float, data: JusticeData
) -> GameState:
    new_value = value
    if (
        resource in NON_NEGATIVE_RESOURCES
        and data.defaults.debt_mode == "clamp_to_zero"
        and new_value < 0
    ):
        new_value = 0
    return replace(state, **{resource: new_value})


def resolve_expr(expr: Any, state: GameState, data: JusticeData) -> float:
    if isinstance(expr, (int, float)):
        return float(expr)
    if isinstance(expr, str):
        case_scale_value, _, functions, variables = _build_numeric_context(state, data)
        value = expr_util.evaluate_numeric(
            expr, expr_util.build_numeric_context(variables, functions)
        )
        return float(value)
    if isinstance(expr, dict):
        raw_expr = str(expr.get("expr"))
        case_scale_value, harbinger_cost_value, functions, variables = (
            _build_numeric_context(state, data)
        )
        value = expr_util.evaluate_numeric(
            raw_expr, expr_util.build_numeric_context(variables, functions)
        )
        if expr.get("scaled_by_case"):
            value *= case_scale_value
        return float(value)
    raise ValueError("Unsupported expression format")


def resolve_probability(prob_spec: Any, state: GameState, data: JusticeData) -> float:
    if isinstance(prob_spec, (int, float)):
        return float(prob_spec)
    if isinstance(prob_spec, str):
        _, _, functions, variables = _build_numeric_context(state, data)
        value = expr_util.evaluate_numeric(
            prob_spec, expr_util.build_numeric_context(variables, functions)
        )
        if data.defaults.default_probability_format == "percent":
            value = value / 100.0
        return float(value)
    if isinstance(prob_spec, dict):
        raw_expr = str(prob_spec.get("expr"))
        format_type = (
            prob_spec.get("format") or data.defaults.default_probability_format
        )
        case_scale_value, harbinger_cost_value, functions, variables = (
            _build_numeric_context(state, data)
        )
        value = expr_util.evaluate_numeric(
            raw_expr, expr_util.build_numeric_context(variables, functions)
        )
        if format_type == "percent":
            value = value / 100.0
        return float(value)
    raise ValueError("Unsupported probability format")


def _build_numeric_context(
    state: GameState,
    data: JusticeData,
) -> tuple[float, float, Mapping[str, Any], Mapping[str, Any]]:
    functions = {
        "ceil": math.ceil,
        "floor": math.floor,
        "min": min,
        "max": max,
        "abs": abs,
    }
    variables = {
        "case_index": state.case_index,
        "coins": state.coins,
        "pop": state.pop,
        "mh": state.mh,
        "dismissals": state.dismissals,
        "retirement_chests": state.retirement_chests,
    }

    ctx = expr_util.build_numeric_context(variables, functions)
    try:
        case_scale_value = expr_util.evaluate_numeric(
            data.special_rules.case_scale.expr, ctx
        )
    except Exception:
        case_scale_value = harbinger_rules.case_scale(state.case_index)

    variables = dict(variables)
    variables["case_scale"] = case_scale_value
    ctx = expr_util.build_numeric_context(variables, functions)
    try:
        harbinger_cost_value = expr_util.evaluate_numeric(
            data.special_rules.harbinger.cost_expr, ctx
        )
    except Exception:
        harbinger_cost_value = harbinger_rules.harbinger_cost(state.case_index)

    variables["harbinger_cost"] = harbinger_cost_value
    return case_scale_value, harbinger_cost_value, functions, variables
