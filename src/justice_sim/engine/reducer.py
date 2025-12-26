"""Reducer for applying actions to game state."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from justice_sim.engine.effects import (
    NON_NEGATIVE_RESOURCES,
    advance_case,
    apply_effects,
    apply_outcome,
    resolve_expr,
    resolve_probability,
)
from justice_sim.engine.encounter import consume_forced_encounter
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import (
    ChainStep,
    EffectSpec,
    JusticeData,
    OfferSpec,
    OutcomeSpec,
)
from justice_sim.models.state import ForcedEncounter, GameState


class ActionNotAllowed(ValueError):
    """Raised when an action cannot be applied."""


def can_afford_action(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    """Return True if the action is affordable with current resources."""
    return _can_afford_action(state, offer, action, data)


def apply_action(
    state: GameState,
    offer: OfferSpec,
    action: str,
    data: JusticeData,
    rng: Rng,
) -> tuple[GameState, str | None]:
    if state.ended:
        raise ActionNotAllowed("Run has ended")
    if action not in offer.actions_available:
        raise ActionNotAllowed(f"Action '{action}' not available")
    if _blocked_by_status(state, action):
        raise ActionNotAllowed(f"Action '{action}' blocked by status")
    if not _can_afford_action(state, offer, action, data):
        raise ActionNotAllowed("Insufficient funds")

    updated = state
    random_label = None
    if state.required_action and action != state.required_action:
        updated = apply_effects(
            updated, state.required_action_penalty_effects, data, rng
        )
    updated = replace(updated, required_action=None, required_action_penalty_effects=())

    updated = _apply_dismissal_cost(updated, offer, action, data)
    outcome = _select_outcome(offer, action)
    updated, random_label = apply_outcome(updated, outcome, data, rng)

    updated = _apply_harbinger_unpaid_penalty(updated, state, offer, action, data, rng)

    updated = _apply_chain(updated, offer, action, data, rng)
    updated = consume_forced_encounter(updated, offer.id)
    updated = _increment_action_counters(updated, offer, action)
    updated = advance_case(updated, data, rng)
    return updated, random_label


def _select_outcome(offer: OfferSpec, action: str) -> OutcomeSpec:
    if action == "approve":
        return offer.approve
    if action == "reject":
        return offer.reject
    if action == "dismiss":
        return offer.dismiss or offer.reject
    raise ActionNotAllowed(f"Unknown action '{action}'")


def _blocked_by_status(state: GameState, action: str) -> bool:
    return f"cannot_{action}" in state.statuses


def _can_afford_action(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    if action == "dismiss" and state.dismissals <= 0:
        return False
    if offer.allow_insufficient_funds is True:
        return True
    outcome = _select_outcome(offer, action)
    return _resources_affordable(state, outcome, data)


def _apply_dismissal_cost(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> GameState:
    if action != "dismiss":
        return state
    if state.dismissals <= 0:
        return state
    new_value = state.dismissals - 1
    if data.defaults.debt_mode == "clamp_to_zero" and new_value < 0:
        new_value = 0
    return replace(state, dismissals=new_value)


def _resources_affordable(
    state: GameState, outcome: OutcomeSpec, data: JusticeData
) -> bool:
    preview = state
    for effect in outcome.effects:
        preview = _preview_effect(preview, effect, data)
        if _has_negative_resources(preview):
            return False
    return True


def _preview_effect(
    state: GameState, effect: EffectSpec, data: JusticeData
) -> GameState:
    params = effect.params
    if effect.type == "add_resource":
        resource = params.get("resource")
        if resource and hasattr(state, resource):
            amount = resolve_expr(params.get("amount"), state, data)
            return replace(state, **{resource: getattr(state, resource) + amount})
    elif effect.type == "set_resource":
        resource = params.get("resource")
        if resource and hasattr(state, resource):
            value = resolve_expr(params.get("value"), state, data)
            return replace(state, **{resource: value})
    elif effect.type == "multiply_resource":
        resource = params.get("resource")
        if resource and hasattr(state, resource):
            factor = resolve_expr(params.get("factor"), state, data)
            return replace(state, **{resource: getattr(state, resource) * factor})
    elif effect.type == "clamp_resource":
        resource = params.get("resource")
        if resource and hasattr(state, resource):
            value = getattr(state, resource)
            min_value = params.get("min")
            max_value = params.get("max")
            if min_value is not None:
                value = max(value, resolve_expr(min_value, state, data))
            if max_value is not None:
                value = min(value, resolve_expr(max_value, state, data))
            return replace(state, **{resource: value})
    elif effect.type == "random_range_resource":
        resource = params.get("resource")
        min_value = params.get("min")
        if resource and hasattr(state, resource) and min_value is not None:
            try:
                value = getattr(state, resource) + float(min_value)
            except (TypeError, ValueError):
                return state
            return replace(state, **{resource: value})
    return state


def _has_negative_resources(state: GameState) -> bool:
    return any(getattr(state, resource) < 0 for resource in NON_NEGATIVE_RESOURCES)


def _apply_chain(
    state: GameState,
    offer: OfferSpec,
    action: str,
    data: JusticeData,
    rng: Rng,
) -> GameState:
    if not offer.chain:
        return state
    forced = list(state.forced_encounters)
    for step in offer.chain.steps:
        if step.trigger != action:
            continue
        if step.probability is not None:
            probability = resolve_probability(step.probability, state, data)
            if rng.random() > probability:
                continue
        forced.append(
            ForcedEncounter(
                trigger_case_index=state.case_index + step.after_cases,
                offer_id=step.offer_id,
                once=step.once,
            )
        )
    return replace(state, forced_encounters=tuple(forced))


def _increment_action_counters(
    state: GameState, offer: OfferSpec, action: str
) -> GameState:
    counters = dict(state.counters)
    suffix = {
        "approve": "approves",
        "reject": "rejects",
        "dismiss": "dismissals",
    }.get(action, action)
    key = f"{offer.npc_id}_{suffix}"
    counters[key] = counters.get(key, 0) + 1
    alias = _counter_alias(offer.npc_id)
    if alias:
        alias_key = f"{alias}_{suffix}"
        counters[alias_key] = counters.get(alias_key, 0) + 1
    return replace(state, counters=counters)


def _counter_alias(npc_id: str) -> str | None:
    for prefix in ("little_", "the_"):
        if npc_id.startswith(prefix):
            return npc_id[len(prefix) :]
    return None


def _apply_harbinger_unpaid_penalty(
    updated: GameState,
    previous: GameState,
    offer: OfferSpec,
    action: str,
    data: JusticeData,
    rng: Rng,
) -> GameState:
    if offer.id != data.special_rules.harbinger.offer_id:
        return updated
    if action != "approve":
        return updated
    cost = resolve_expr(
        {"expr": data.special_rules.harbinger.cost_expr}, previous, data
    )
    if previous.coins >= cost:
        return updated
    if data.special_rules.harbinger.on_unpaid_effects:
        return apply_effects(
            updated, data.special_rules.harbinger.on_unpaid_effects, data, rng
        )
    return updated
