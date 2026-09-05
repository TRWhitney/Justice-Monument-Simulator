"""Reducer for applying actions to game state."""

from __future__ import annotations

from dataclasses import replace
from math import floor

from justice_sim.engine.effects import (
    MAIN_RESOURCES,
    NON_NEGATIVE_RESOURCES,
    advance_case,
    apply_effects,
    apply_outcome,
    normalize_action_resources,
    normalized_action_resource,
    outcome_additive_resource_cost,
    resolve_expr,
    resolve_probability,
)
from justice_sim.engine.encounter import consume_forced_encounter
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import (
    EffectSpec,
    JusticeData,
    OfferSpec,
    OutcomeSpec,
)
from justice_sim.models.state import (
    ActionTrigger,
    EncounterOverride,
    EncounterTrigger,
    ForcedEncounter,
    GameState,
)
from justice_sim.util import expr as expr_util


class ActionNotAllowed(ValueError):
    """Raised when an action cannot be applied."""


def can_afford_action(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    """Return True if the action is affordable with current resources."""
    return _can_afford_action(state, offer, action, data)


def is_action_blocked(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    """Return True if the action is blocked by status effects."""
    return _blocked_by_status(state, offer, action, data)


def preview_state_after_encounter_triggers(
    state: GameState, offer: OfferSpec, data: JusticeData, rng: Rng
) -> GameState:
    """Return the state after applying encounter triggers for the offer."""
    if state.ended or state.mh <= 0:
        return state
    return _apply_encounter_triggers(state, offer, data, rng)


def preview_state_before_outcome(
    state: GameState,
    offer: OfferSpec,
    action: str,
    data: JusticeData,
    rng: Rng,
    *,
    encounter_start: GameState | None = None,
) -> GameState:
    """Prepare an action using the same ordering as the reducer.

    Preview callers must supply a cloned RNG so preparation cannot consume the
    live run's randomness. The returned state has not applied the outcome yet.
    Supply the original encounter_start only when state already includes its
    arrival triggers. Rollouts use it to choose after a realized random arrival
    without applying permanent triggers twice or consuming newly added overrides.
    """
    if state.ended or state.mh <= 0:
        raise ActionNotAllowed("Run has ended")
    updated = (
        state
        if encounter_start is not None
        else _apply_encounter_triggers(state, offer, data, rng)
    )
    if updated.ended or updated.mh <= 0:
        raise ActionNotAllowed("Run has ended")
    if action not in offer.actions_available:
        raise ActionNotAllowed(f"Action '{action}' not available")
    if _blocked_by_status(updated, offer, action, data):
        raise ActionNotAllowed(f"Action '{action}' blocked by status")
    if not _can_afford_action(updated, offer, action, data):
        raise ActionNotAllowed("Insufficient funds")
    if updated.required_action and action != updated.required_action:
        updated = apply_effects(
            updated, updated.required_action_penalty_effects, data, rng
        )
    if updated.required_action is not None or updated.required_action_penalty_effects:
        updated = replace(
            updated, required_action=None, required_action_penalty_effects=()
        )
    updated = _apply_dismissal_cost(updated, offer, action, data)
    if action == "approve" and offer.approval_triggers_first:
        updated = _apply_action_triggers(updated, offer, action, data, rng)
    return updated


def action_may_survive(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    """Keep uncertain actions available; one random loss cannot prove game over."""
    if state.ended or state.mh <= 0 or action not in offer.actions_available:
        return False
    rng = Rng(0)
    try:
        next_state, _ = apply_action(state, offer, action, data, rng)
    except ActionNotAllowed:
        return rng.state().draws > 0
    return rng.state().draws > 0 or (not next_state.ended and next_state.mh > 0)


def apply_action(
    state: GameState,
    offer: OfferSpec,
    action: str,
    data: JusticeData,
    rng: Rng,
    *,
    encounter_start: GameState | None = None,
) -> tuple[GameState, str | None]:
    outcome = _select_outcome(offer, action)
    return _apply_action_with_outcome(
        state,
        offer,
        action,
        outcome,
        data,
        rng,
        random_label_override=None,
        encounter_start=encounter_start,
    )


def skip_case(state: GameState, data: JusticeData, rng: Rng) -> GameState:
    if state.ended or state.mh <= 0:
        raise ActionNotAllowed("Run has ended")
    return advance_case(state, data, rng)


def apply_action_with_outcome(
    state: GameState,
    offer: OfferSpec,
    action: str,
    outcome: OutcomeSpec,
    data: JusticeData,
    rng: Rng,
    random_label: str | None = None,
    *,
    encounter_start: GameState | None = None,
) -> tuple[GameState, str | None]:
    return _apply_action_with_outcome(
        state,
        offer,
        action,
        outcome,
        data,
        rng,
        random_label_override=random_label,
        encounter_start=encounter_start,
    )


def _apply_action_with_outcome(
    state: GameState,
    offer: OfferSpec,
    action: str,
    outcome: OutcomeSpec,
    data: JusticeData,
    rng: Rng,
    random_label_override: str | None,
    encounter_start: GameState | None = None,
) -> tuple[GameState, str | None]:
    encounter_overrides_at_start = (
        state if encounter_start is None else encounter_start
    ).encounter_overrides
    updated = preview_state_before_outcome(
        state, offer, action, data, rng, encounter_start=encounter_start
    )
    return _resolve_prepared_action(
        updated,
        offer,
        action,
        outcome,
        data,
        rng,
        encounter_overrides_at_start,
        random_label_override,
    )


def _resolve_prepared_action(
    updated: GameState,
    offer: OfferSpec,
    action: str,
    outcome: OutcomeSpec,
    data: JusticeData,
    rng: Rng,
    encounter_overrides_at_start: tuple[EncounterOverride, ...],
    random_label_override: str | None = None,
) -> tuple[GameState, str | None]:
    pre_action_state = updated
    updated, random_label = apply_outcome(updated, outcome, data, rng)
    if random_label_override is not None:
        random_label = random_label_override

    if action != "approve" or not offer.approval_triggers_first:
        updated = _apply_action_triggers(updated, offer, action, data, rng)
    updated = _apply_harbinger_unpaid_penalty(
        updated, pre_action_state, offer, action, data, rng
    )

    updated = _apply_chain(updated, offer, action, data, rng)
    updated = consume_forced_encounter(updated, offer.id)
    updated = _increment_action_counters(updated, offer, action)
    updated = _consume_encounter_overrides(updated, offer, encounter_overrides_at_start)
    updated = normalize_action_resources(updated, data)
    updated = advance_case(updated, data, rng)
    return updated, random_label


def action_preserves_health(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    """Evaluate the scoring probe without constructing irrelevant final state.

    This has the same health/ended result as apply_action with Rng(0). Complex
    outcomes finish through the shared reducer, using the already prepared RNG.
    It is a scoring probe, not a proof of survival for unresolved randomness.
    """
    outcome = _select_outcome(offer, action)
    rng = Rng(0)
    prepared = preview_state_before_outcome(state, offer, action, data, rng)
    simple = (
        outcome.random is None
        and all(
            effect.schedule_after_cases is None
            and (
                (
                    effect.type
                    in {
                        "add_resource",
                        "set_resource",
                        "multiply_resource",
                        "clamp_resource",
                    }
                    and effect.params.get("resource") in MAIN_RESOURCES - {"mh"}
                )
                or effect.type in {"set_counter", "increment_counter", "clear_counter"}
            )
            for effect in outcome.effects
        )
        and not any(
            event.trigger_case_index == prepared.case_index + 1
            for event in prepared.scheduled_events
        )
        and (
            (action == "approve" and offer.approval_triggers_first)
            or not any(
                trigger.action in {"any", action}
                and (not trigger.offer_id or trigger.offer_id == offer.id)
                and (not trigger.npc_id or trigger.npc_id == offer.npc_id)
                for trigger in prepared.action_triggers
            )
        )
        and not (
            action == "approve"
            and offer.id == data.special_rules.harbinger.offer_id
            and data.special_rules.harbinger.on_unpaid_effects
            and prepared.coins
            < outcome_additive_resource_cost(prepared, offer.approve, "coins", data)
        )
    )
    if simple:
        return (
            normalized_action_resource(prepared, "mh", data) >= state.mh
            and not prepared.ended
        )
    result, _ = _resolve_prepared_action(
        prepared, offer, action, outcome, data, rng, state.encounter_overrides
    )
    return result.mh >= state.mh and not result.ended


def _select_outcome(offer: OfferSpec, action: str) -> OutcomeSpec:
    if action == "approve":
        return offer.approve
    if action == "reject":
        return offer.reject
    if action == "dismiss":
        return offer.dismiss or offer.reject
    raise ActionNotAllowed(f"Unknown action '{action}'")


def _blocked_by_status(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    if f"cannot_{action}" in state.statuses:
        return True
    if action == "dismiss" and "cannot_dismiss_harbinger" in state.statuses:
        grateful_offer_id = None
        if data.special_rules.gratefulbinger:
            grateful_offer_id = data.special_rules.gratefulbinger.offer_id
        if offer.id == grateful_offer_id:
            return False
        harbinger_ids = {data.special_rules.harbinger.offer_id}
        harbinger_ids.update(data.special_rules.harbinger.offer_pool)
        if offer.id in harbinger_ids:
            return True
        base_harbinger = data.offers_by_id.get(data.special_rules.harbinger.offer_id)
        if base_harbinger and offer.npc_id == base_harbinger.npc_id:
            return True
    return False


def _can_afford_action(
    state: GameState, offer: OfferSpec, action: str, data: JusticeData
) -> bool:
    if action == "dismiss" and state.dismissals <= 0:
        return False
    if offer.payment_resource is not None:
        if action != "approve" or offer.payment_resource == "none":
            return True
        resource = offer.payment_resource
        cost = outcome_additive_resource_cost(state, offer.approve, resource, data)
        return getattr(state, resource) >= cost
    if offer.allow_insufficient_funds is True:
        return True
    outcome = _select_outcome(offer, action)
    allow_negative = {"pop"} if action == "reject" else set()
    return _resources_affordable(
        state, outcome, data, allow_negative_resources=allow_negative
    )


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
    state: GameState,
    outcome: OutcomeSpec,
    data: JusticeData,
    *,
    allow_negative_resources: set[str] | None = None,
) -> bool:
    allow_negative_resources = allow_negative_resources or set()
    preview = state
    for effect in outcome.effects:
        if effect.when and not _predicate_allows(effect.when, preview, data):
            continue
        if effect.schedule_after_cases is not None:
            continue
        unrounded = _preview_effect(preview, effect, data)
        # Match whole-resource deductions without clamping away unpaid costs.
        if unrounded is not preview:
            preview = replace(
                unrounded,
                **{
                    resource: floor(getattr(unrounded, resource) + 0.5)
                    for resource in MAIN_RESOURCES
                    if getattr(unrounded, resource) != getattr(preview, resource)
                },
            )
        if _has_negative_resources(preview, allow_negative_resources):
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
    elif effect.type == "random_exchange":
        take_resource = params.get("take_resource")
        give_resource = params.get("give_resource")
        if not take_resource or not give_resource:
            return state
        if not hasattr(state, take_resource) or not hasattr(state, give_resource):
            return state
        min_value = resolve_expr(params.get("min"), state, data)
        preview = replace(
            state,
            **{
                take_resource: getattr(state, take_resource) - min_value,
                give_resource: getattr(state, give_resource) + min_value,
            },
        )
        return preview
    return state


def _has_negative_resources(
    state: GameState, allow_negative_resources: set[str] | None = None
) -> bool:
    allow_negative_resources = allow_negative_resources or set()
    return any(
        getattr(state, resource) < 0
        for resource in NON_NEGATIVE_RESOURCES
        if resource not in allow_negative_resources
    )


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
            if rng.random() >= probability:
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
    cost = outcome_additive_resource_cost(previous, offer.approve, "coins", data)
    if previous.coins >= cost:
        return updated
    if data.special_rules.harbinger.on_unpaid_effects:
        return apply_effects(
            updated, data.special_rules.harbinger.on_unpaid_effects, data, rng
        )
    return updated


def _apply_encounter_triggers(
    state: GameState, offer: OfferSpec, data: JusticeData, rng: Rng
) -> GameState:
    state = apply_effects(state, offer.arrival_effects, data, rng)
    if not state.encounter_triggers:
        return state
    current = state
    triggers = state.encounter_triggers
    if data.special_rules.client_encounters:
        # Scaring happens before NPC-specific arrivals, regardless of which
        # agreement was accepted first. Keep saved trigger payloads compatible.
        triggers = tuple(sorted(triggers, key=lambda t: t.label != "ghost_scare_pop"))
    for trigger in triggers:
        if trigger not in current.encounter_triggers:
            continue
        if trigger.offer_id and trigger.offer_id != offer.id:
            continue
        if trigger.npc_id and trigger.npc_id != offer.npc_id:
            continue
        if trigger.when and not _predicate_allows(trigger.when, current, data):
            continue
        current = apply_effects(current, trigger.effects, data, rng)
        if data.special_rules.client_encounters and trigger.label == "ghost_scare_pop":
            # This is an explicit client arrival clamp, not the PermaPop floor.
            current = replace(current, pop=max(0, current.pop))
        current = _decrement_encounter_trigger_use(current, trigger)
    return current


def _apply_action_triggers(
    state: GameState,
    offer: OfferSpec,
    action: str,
    data: JusticeData,
    rng: Rng,
) -> GameState:
    if not state.action_triggers:
        return state
    current = state
    for trigger in tuple(state.action_triggers):
        if trigger not in current.action_triggers:
            continue
        if trigger.action not in {"any", action}:
            continue
        if trigger.offer_id and trigger.offer_id != offer.id:
            continue
        if trigger.npc_id and trigger.npc_id != offer.npc_id:
            continue
        if trigger.when and not _predicate_allows(trigger.when, current, data):
            continue
        current = apply_effects(current, trigger.effects, data, rng)
        current = _decrement_action_trigger_use(current, trigger)
    return current


def _consume_encounter_overrides(
    state: GameState,
    offer: OfferSpec,
    encounter_overrides_at_start: tuple[EncounterOverride, ...],
) -> GameState:
    if not state.encounter_overrides:
        return state
    existing_ids = {id(override) for override in encounter_overrides_at_start}
    remaining: list[EncounterOverride] = []
    for override in state.encounter_overrides:
        if id(override) not in existing_ids:
            remaining.append(override)
            continue
        if override.offer_id and override.offer_id != offer.id:
            remaining.append(override)
            continue
        if override.npc_id and override.npc_id != offer.npc_id:
            remaining.append(override)
            continue
        uses = override.remaining_uses
        if uses is None or uses < 0:
            remaining.append(override)
            continue
        uses -= 1
        if uses > 0:
            remaining.append(replace(override, remaining_uses=uses))
    return replace(state, encounter_overrides=tuple(remaining))


def _decrement_action_trigger_use(
    state: GameState, trigger: ActionTrigger
) -> GameState:
    uses = trigger.remaining_uses
    if uses is None or uses < 0:
        return state
    updated = []
    decremented = False
    for current in state.action_triggers:
        if not decremented and current == trigger:
            remaining = uses - 1
            decremented = True
            if remaining > 0:
                updated.append(replace(current, remaining_uses=remaining))
            continue
        updated.append(current)
    if not decremented:
        return state
    return replace(state, action_triggers=tuple(updated))


def _decrement_encounter_trigger_use(
    state: GameState, trigger: EncounterTrigger
) -> GameState:
    uses = trigger.remaining_uses
    if uses is None or uses < 0:
        return state
    updated = []
    decremented = False
    for current in state.encounter_triggers:
        if not decremented and current == trigger:
            remaining = uses - 1
            decremented = True
            if remaining > 0:
                updated.append(replace(current, remaining_uses=remaining))
            continue
        updated.append(current)
    if not decremented:
        return state
    return replace(state, encounter_triggers=tuple(updated))


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
