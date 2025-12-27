"""Offer summary rendering helpers shared by CLI and GUI."""

from __future__ import annotations

import math
import re
from typing import Iterable

from justice_sim.engine.effects import (
    MAIN_RESOURCES,
    NON_NEGATIVE_RESOURCES,
    resolve_expr,
    resolve_probability,
)
from justice_sim.models.offer import (
    BernoulliSpec,
    CategoricalSpec,
    EffectSpec,
    JusticeData,
    OutcomeSpec,
)
from justice_sim.models.state import GameState
from justice_sim.util import expr as expr_util


_RESOURCE_LABELS = {
    "coins": "coins",
    "pop": "pop",
    "mh": "health",
    "dismissals": "dismissals",
    "retirement_chests": "chests",
}
_HIDDEN_COUNTERS = {
    "fizarre_drink_approves",
}
_HIDDEN_ENCOUNTER_TRIGGERS = {
    "ghost_scare_pop",
}
_STATUS_DESCRIPTIONS = {
    "ghost_scare": "Scaring legalized: pop -1 each case",
}
_STATUS_CLEAR_DESCRIPTIONS = {
    "ghost_scare": "Scaring ban reinstated",
}


def summarize_outcome(outcome: OutcomeSpec, state: GameState, data: JusticeData) -> str:
    parts = []
    immediate_effects: list[EffectSpec] = []
    deferred_effects: list[EffectSpec] = []
    for effect in outcome.effects:
        if _is_deferred_effect(effect.type):
            deferred_effects.append(effect)
        else:
            immediate_effects.append(effect)
    parts.extend(_summarize_effects(immediate_effects, state, data))
    parts.extend(_summarize_effects(deferred_effects, state, data))
    if outcome.random:
        parts.append(_summarize_random_outcomes(outcome.random, state, data))
    return "; ".join(parts) if parts else "No effect"


def summarize_offer(
    offer, state: GameState, data: JusticeData
) -> tuple[str, str, str | None]:
    approve_summary = summarize_outcome(offer.approve, state, data)
    reject_summary = summarize_outcome(offer.reject, state, data)
    dismiss_summary = (
        summarize_outcome(offer.dismiss, state, data) if offer.dismiss else None
    )
    return approve_summary, reject_summary, dismiss_summary


def _predicate_allows(predicate: object, state: GameState, data: JusticeData) -> bool:
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


def _summarize_effects(
    effects: Iterable[EffectSpec], state: GameState, data: JusticeData
) -> list[str]:
    parts: list[str] = []
    for effect in effects:
        if effect.when and not _predicate_allows(effect.when, state, data):
            continue
        params = effect.params
        if effect.type == "add_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            parts.append(
                f"{_format_delta(params.get('amount'), state, data, params.get('resource'))} {resource}"
            )
        elif effect.type == "set_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            value = _format_value(
                params.get("value"), state, data, params.get("resource")
            )
            parts.append(f"set {resource}={value}")
        elif effect.type == "clamp_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            min_value = params.get("min")
            max_value = params.get("max")
            if min_value is not None and max_value is not None:
                min_text = _format_value(min_value, state, data)
                max_text = _format_value(max_value, state, data)
                parts.append(f"{resource} {min_text}-{max_text}")
            elif min_value is not None:
                min_text = _format_value(min_value, state, data)
                parts.append(f"{resource} to at least {min_text}")
            elif max_value is not None:
                max_text = _format_value(max_value, state, data)
                parts.append(f"{resource} to at most {max_text}")
            else:
                parts.append(f"{resource} clamp")
        elif effect.type == "multiply_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            resource_key = params.get("resource")
            factor_value = _resolve_amount(params.get("factor"), state, data)
            if factor_value is not None and factor_value == 0:
                parts.append(f"set {resource}=0")
            else:
                factor = _format_value(params.get("factor"), state, data)
                result = _multiply_result(resource_key, factor_value, state, data)
                if result is not None:
                    parts.append(f"{resource} x{factor} -> {result:g}")
                else:
                    parts.append(f"{resource} x{factor}")
        elif effect.type == "random_range_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            min_value = _format_range_value(
                params.get("min"), params.get("max"), state, data
            )
            parts.append(f"{min_value} {resource}")
        elif effect.type == "random_exchange":
            take_resource = _RESOURCE_LABELS.get(
                params.get("take_resource"), str(params.get("take_resource"))
            )
            give_resource = _RESOURCE_LABELS.get(
                params.get("give_resource"), str(params.get("give_resource"))
            )
            amount_range = _format_range_value(
                params.get("min"), params.get("max"), state, data
            ).lstrip("+")
            parts.append(
                f"random {amount_range} {take_resource} for equal {give_resource}"
            )
        elif effect.type == "swap_resources":
            resource_a = _RESOURCE_LABELS.get(
                params.get("resource_a"), str(params.get("resource_a"))
            )
            resource_b = _RESOURCE_LABELS.get(
                params.get("resource_b"), str(params.get("resource_b"))
            )
            parts.append(f"swap {resource_a}/{resource_b}")
        elif effect.type == "add_status":
            status = str(params.get("status", ""))
            description = _STATUS_DESCRIPTIONS.get(status)
            if description:
                parts.append(description)
            else:
                status_name = _humanize_label(status)
                duration = effect.duration_cases
                if duration is not None and duration >= 0:
                    parts.append(f"status {status_name} ({duration} cases)")
                else:
                    parts.append(f"status {status_name}")
        elif effect.type == "remove_status":
            status = str(params.get("status", ""))
            description = _STATUS_CLEAR_DESCRIPTIONS.get(status)
            if description:
                parts.append(description)
            else:
                parts.append(f"remove {_humanize_label(status)}")
        elif effect.type == "set_resource_floor":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            value = _format_value(params.get("min"), state, data)
            parts.append(f"{resource} can't go below {value}")
        elif effect.type == "clear_resource_floor":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            parts.append(f"remove {resource} minimum")
        elif effect.type == "add_flag":
            continue
        elif effect.type == "remove_flag":
            continue
        elif effect.type == "require_next_action":
            action = _humanize_label(params.get("action"))
            penalty_effects = params.get("penalty_effects", [])
            if penalty_effects:
                penalties = _summarize_effects(
                    (_effect_from_dict(effect_dict) for effect_dict in penalty_effects),
                    state,
                    data,
                )
                penalty_summary = ", ".join(penalties) if penalties else "penalty"
                parts.append(f"must {action} next (or: {penalty_summary})")
            else:
                parts.append(f"must {action} next")
        elif effect.type == "schedule_effects":
            after_cases = int(params.get("after_cases", 0))
            scheduled_effects = _summarize_effects(
                (
                    _effect_from_dict(effect_dict)
                    for effect_dict in params.get("effects", [])
                ),
                state,
                data,
            )
            summary = ", ".join(scheduled_effects) if scheduled_effects else "effects"
            prefix = "next case" if after_cases == 1 else f"in {after_cases} cases"
            parts.append(f"{prefix}: {summary}")
        elif effect.type == "schedule_recurring_effects":
            after_cases = int(params.get("after_cases", 0))
            every_cases = int(params.get("every_cases", 1))
            repeat = int(params.get("repeat", 1))
            recurring_effects = _summarize_effects(
                (
                    _effect_from_dict(effect_dict)
                    for effect_dict in params.get("effects", [])
                ),
                state,
                data,
            )
            summary = ", ".join(recurring_effects) if recurring_effects else "effects"
            if every_cases == 1 and repeat > 0:
                case_label = "case" if repeat == 1 else "cases"
                if after_cases <= 1:
                    parts.append(f"{summary} for next {repeat} {case_label}")
                else:
                    parts.append(
                        f"{summary} for next {repeat} {case_label} "
                        f"(starting in {after_cases} cases)"
                    )
            else:
                cadence = (
                    "every case" if every_cases == 1 else f"every {every_cases} cases"
                )
                if repeat > 0:
                    cadence = f"{cadence} x{repeat}"
                if after_cases > 0:
                    parts.append(f"{cadence} (start {after_cases}): {summary}")
                else:
                    parts.append(f"{cadence}: {summary}")
        elif effect.type == "add_action_trigger":
            action = params.get("action", "any")
            summary = _summarize_trigger_effects(params.get("effects", []), state, data)
            npc_name = _format_entity_name(params.get("npc_id"), data)
            offer_name = _format_entity_name(params.get("offer_id"), data)
            target = npc_name or offer_name
            remaining = _format_remaining_uses(params.get("remaining_uses"))
            target_suffix = f" @ {target}" if target else ""
            parts.append(
                f"on {_humanize_label(action)}{target_suffix}: {summary}{remaining}"
            )
        elif effect.type == "add_encounter_trigger":
            label = params.get("label")
            if label in _HIDDEN_ENCOUNTER_TRIGGERS:
                continue
            npc_id = params.get("npc_id") or params.get("offer_id") or "encounter"
            npc_name = _format_entity_name(npc_id, data)
            summary = _summarize_trigger_effects(params.get("effects", []), state, data)
            remaining = _format_remaining_uses(params.get("remaining_uses"))
            parts.append(f"on {npc_name}: {summary}{remaining}")
        elif effect.type == "add_encounter_override":
            target = params.get("offer_id") or params.get("npc_id") or "encounter"
            target_name = _format_entity_name(target, data)
            remaining = _format_remaining_uses(params.get("remaining_uses"))
            probability = _format_probability(params.get("probability"), state, data)
            if probability:
                parts.append(f"{probability} chance {target_name}{remaining}")
            else:
                parts.append(f"force {target_name}{remaining}")
        elif effect.type == "remove_action_trigger":
            label = params.get("label")
            if label:
                parts.append(f"remove trigger {_humanize_label(label)}")
            else:
                parts.append("remove action trigger")
        elif effect.type == "remove_encounter_trigger":
            label = params.get("label")
            if label in _HIDDEN_ENCOUNTER_TRIGGERS:
                continue
            if label:
                parts.append(f"remove trigger {_humanize_label(label)}")
            else:
                parts.append("remove encounter trigger")
        elif effect.type == "remove_encounter_override":
            label = params.get("label")
            if label:
                parts.append(f"remove override {_humanize_label(label)}")
            else:
                parts.append("remove override")
        elif effect.type == "modify_encounter_weights":
            parts.append("encounter weights updated")
        elif effect.type in {"set_counter", "add_counter", "clear_counter"}:
            counter = str(params.get("counter", ""))
            if counter in _HIDDEN_COUNTERS:
                continue
            counter_name = _humanize_label(counter)
            if effect.type == "set_counter":
                value = _format_value(params.get("value"), state, data)
                parts.append(f"{counter_name}={value}")
            elif effect.type == "add_counter":
                value = _format_delta(params.get("amount"), state, data)
                parts.append(f"{counter_name} {value}")
            else:
                parts.append(f"clear {counter_name}")
        elif effect.type == "end_run":
            parts.append("end run")
        elif effect.type == "raw_effect":
            raw = params.get("raw")
            if raw:
                parts.append(str(raw))
    return parts


def _summarize_random_outcomes(
    random_spec: BernoulliSpec | CategoricalSpec,
    state: GameState,
    data: JusticeData,
) -> str:
    choices: list[tuple[EffectSpec, ...]] = []
    if isinstance(random_spec, BernoulliSpec):
        choices = [random_spec.then_effects, random_spec.else_effects]
    elif isinstance(random_spec, CategoricalSpec):
        choices = [choice.effects for choice in random_spec.choices]
    summaries: list[str] = []
    for effects in choices:
        parts = _summarize_effects(effects, state, data)
        summaries.append(", ".join(parts) if parts else "no effect")
    if not summaries:
        return "random outcome"
    return "random: " + " OR ".join(summaries)


def _is_deferred_effect(effect_type: str) -> bool:
    return effect_type in {
        "add_action_trigger",
        "add_encounter_trigger",
        "add_encounter_override",
        "schedule_effects",
        "schedule_recurring_effects",
        "require_next_action",
        "modify_encounter_weights",
        "remove_action_trigger",
        "remove_encounter_trigger",
        "remove_encounter_override",
    }


def _effect_from_dict(raw: dict) -> EffectSpec:
    return EffectSpec(
        type=str(raw.get("type")),
        params=dict(raw.get("params", {})),
        when=raw.get("when"),
        duration_cases=raw.get("duration_cases"),
        schedule_after_cases=raw.get("schedule_after_cases"),
        label=raw.get("label"),
    )


def _summarize_trigger_effects(
    raw_effects: Iterable[dict], state: GameState, data: JusticeData
) -> str:
    groups = _group_effects_by_when(raw_effects)
    summaries: list[str] = []
    for when_value, effects in groups:
        primary_effects, cleanup_text = _split_trigger_effects(effects)
        parts = _summarize_effects(primary_effects, state, data)
        if cleanup_text:
            parts.append(cleanup_text)
        if not parts:
            continue
        summary = ", ".join(parts)
        if when_value:
            condition = _humanize_condition(when_value)
            summary = f"if {condition}: {summary}"
        summaries.append(summary)
    return "; ".join(summaries) if summaries else "effects"


def _group_effects_by_when(
    raw_effects: Iterable[dict],
) -> list[tuple[object | None, list[dict]]]:
    groups: list[tuple[str | None, object | None, list[dict]]] = []
    for raw in raw_effects:
        when_value = raw.get("when")
        key = str(when_value) if when_value is not None else None
        for existing_key, _, bucket in groups:
            if existing_key == key:
                bucket.append(raw)
                break
        else:
            groups.append((key, when_value, [raw]))
    return [(when_value, bucket) for _, when_value, bucket in groups]


def _split_trigger_effects(
    raw_effects: Iterable[dict],
) -> tuple[list[EffectSpec], str | None]:
    cleanup_types = {
        "remove_action_trigger",
        "remove_encounter_trigger",
        "remove_encounter_override",
    }
    primary_raw = []
    remove_present = False
    clear_counters: list[str] = []
    for raw in raw_effects:
        effect_type = raw.get("type")
        if effect_type in cleanup_types:
            remove_present = True
            continue
        if effect_type == "clear_counter":
            counter = raw.get("params", {}).get("counter")
            if counter:
                clear_counters.append(str(counter))
            continue
        primary_raw.append(raw)
    cleanup_text = None
    if remove_present:
        cleanup_text = "end deal"
    elif clear_counters:
        if len(clear_counters) == 1:
            cleanup_text = f"clear {_humanize_label(clear_counters[0])}"
        else:
            cleanup_text = "clear counters"
    effects = [_effect_from_dict(raw) for raw in primary_raw]
    return effects, cleanup_text


def _format_entity_name(identifier: str | None, data: JusticeData) -> str:
    if not identifier:
        return ""
    npc = data.npcs_by_id.get(identifier)
    if npc:
        return npc.name
    offer = data.offers_by_id.get(identifier)
    if offer:
        return offer.title
    return _humanize_label(identifier)


def _humanize_label(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split())


def _humanize_condition(value: object) -> str:
    if value is None:
        return ""
    text = str(value)

    def _replace(match: re.Match) -> str:
        return _humanize_label(match.group(2))

    text = re.sub(r"\b(counters|flags|statuses)\.([A-Za-z0-9_]+)", _replace, text)
    return text.replace("_", " ")


def _format_remaining_uses(remaining: object) -> str:
    if remaining is None:
        return ""
    try:
        remaining_value = int(remaining)
    except (TypeError, ValueError):
        return ""
    if remaining_value <= 0:
        return ""
    if remaining_value == 1:
        return " (once)"
    return f" (x{remaining_value})"


def _format_delta(
    amount: object,
    state: GameState,
    data: JusticeData,
    resource: object | None = None,
) -> str:
    value = _resolve_amount(amount, state, data)
    if value is None:
        return str(amount)
    if resource in MAIN_RESOURCES:
        value = math.ceil(value)
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:g}"


def _format_value(
    amount: object,
    state: GameState,
    data: JusticeData,
    resource: object | None = None,
) -> str:
    value = _resolve_amount(amount, state, data)
    if value is None:
        return str(amount)
    if resource in MAIN_RESOURCES:
        value = math.ceil(value)
    return f"{value:g}"


def _multiply_result(
    resource: object,
    factor_value: float | None,
    state: GameState,
    data: JusticeData,
) -> float | None:
    if factor_value is None or resource is None:
        return None
    try:
        current = float(getattr(state, str(resource)))
    except (AttributeError, TypeError, ValueError):
        return None
    value = current * factor_value
    resource_key = str(resource)
    if (
        resource_key in NON_NEGATIVE_RESOURCES
        and data.defaults.debt_mode == "clamp_to_zero"
        and value < 0
    ):
        value = 0.0
    floor = state.resource_floors.get(resource_key)
    if floor is not None and value < floor:
        value = float(floor)
    if resource_key in MAIN_RESOURCES:
        value = math.ceil(value)
    return value


def _format_range_value(
    min_value: object, max_value: object, state: GameState, data: JusticeData
) -> str:
    min_resolved = _resolve_amount(min_value, state, data)
    max_resolved = _resolve_amount(max_value, state, data)
    if min_resolved is None or max_resolved is None:
        return f"{min_value}-{max_value}"
    sign = "+" if min_resolved >= 0 else ""
    return f"{sign}{min_resolved:g}-{max_resolved:g}"


def _resolve_amount(
    amount: object, state: GameState, data: JusticeData
) -> float | None:
    if amount is None:
        return None
    try:
        return float(resolve_expr(amount, state, data))
    except Exception:
        return None


def _format_probability(
    spec: object, state: GameState, data: JusticeData
) -> str | None:
    if spec is None:
        return None
    try:
        value = resolve_probability(spec, state, data)
    except Exception:
        return None
    percent = value * 100.0
    if abs(percent - round(percent)) < 1e-6:
        return f"{int(round(percent))}%"
    return f"{percent:.1f}%"
