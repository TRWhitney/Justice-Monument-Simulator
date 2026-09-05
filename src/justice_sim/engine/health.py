"""Bounded reuse of reducer health probes with proven narrow dependencies."""

from collections import OrderedDict

from justice_sim.engine.effects import MAIN_RESOURCES, is_case_only_value
from justice_sim.engine import reducer
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import GameState


_RESOURCE_PARAMETERS = {
    "add_resource": ("amount",),
    "set_resource": ("value",),
    "multiply_resource": ("factor",),
    "clamp_resource": ("min", "max"),
}
_COUNTER_PARAMETERS = {
    "set_counter": ("value",),
    "increment_counter": ("amount",),
    "clear_counter": (),
}


def _probe_resources(
    data: JusticeData, offer: OfferSpec, action: str
) -> tuple[str, ...] | None:
    # Legacy affordability scans all resources, including unchanged negatives.
    # Keep it, unknown actions, and chains on the complete reducer path.
    if offer.payment_resource not in MAIN_RESOURCES | {"none"} or offer.chain:
        return None
    if action not in {"approve", "reject", "dismiss"}:
        return None
    outcome = (
        (offer.dismiss or offer.reject)
        if action == "dismiss"
        else getattr(offer, action)
    )
    if outcome.random is not None:
        return None
    resources = {"mh"}
    if action == "dismiss":
        resources.add("dismissals")
    if action == "approve" and offer.payment_resource != "none":
        resources.add(offer.payment_resource)
    effects = offer.arrival_effects + outcome.effects
    if action == "approve" and offer.id == data.special_rules.harbinger.offer_id:
        resources.add("coins")
        effects += data.special_rules.harbinger.on_unpaid_effects
    for effect in effects:
        if effect.when or effect.schedule_after_cases is not None:
            return None
        if effect.type in _RESOURCE_PARAMETERS:
            resource = effect.params.get("resource")
            if resource not in MAIN_RESOURCES:
                return None
            resources.add(resource)
            parameters = _RESOURCE_PARAMETERS[effect.type]
        elif effect.type in _COUNTER_PARAMETERS:
            parameters = _COUNTER_PARAMETERS[effect.type]
        else:
            return None
        for name in parameters:
            value = effect.params.get(name)
            if value is not None and not is_case_only_value(value, data):
                return None
    return tuple(sorted(resources))


class HealthProbeCache:
    """Cache simple per-action probes; complex state always uses the reducer.

    Profiles belong to the immutable offer definitions in one data lifetime.
    Resource-dependent formulas, random effects, matching triggers, requirements,
    and due events deliberately bypass this cache. Eligibility conditions belong
    to encounter selection and are not evaluated by an action health probe.
    """

    def __init__(self, data: JusticeData, max_entries: int = 10000) -> None:
        self.data = data
        self.max_entries = max_entries
        self._profiles = {
            (offer.id, action): (offer, _probe_resources(data, offer, action))
            for offer in data.offers_by_id.values()
            for action in offer.actions_available
        }
        self._cache: OrderedDict[tuple, bool] = OrderedDict()

    def can_preserve_health(
        self, state: GameState, offer: OfferSpec, action: str
    ) -> bool:
        profile = self._profiles.get((offer.id, action))
        resources = profile[1] if profile is not None and profile[0] is offer else None
        key = None
        if resources is not None and not (
            state.required_action
            or state.required_action_penalty_effects
            or any(
                e.trigger_case_index == state.case_index + 1
                for e in state.scheduled_events
            )
            or any(
                (not t.offer_id or t.offer_id == offer.id)
                and (not t.npc_id or t.npc_id == offer.npc_id)
                for t in state.encounter_triggers
            )
            or any(
                t.action in {"any", action}
                and (not t.offer_id or t.offer_id == offer.id)
                and (not t.npc_id or t.npc_id == offer.npc_id)
                for t in state.action_triggers
            )
        ):
            key = (
                offer.id,
                action,
                state.case_index,
                state.ended,
                tuple(getattr(state, resource) for resource in resources),
                tuple(state.resource_floors.get(resource) for resource in resources),
                f"cannot_{action}" in state.statuses,
                "cannot_dismiss_harbinger" in state.statuses
                if action == "dismiss"
                else False,
            )
            cached = self._cache.get(key)
            if cached is not None:
                return cached
        try:
            result = reducer.action_preserves_health(state, offer, action, self.data)
        except reducer.ActionNotAllowed:
            result = False
        if key is not None and self.max_entries > 0:
            if len(self._cache) >= self.max_entries:
                self._cache.popitem(last=False)
            self._cache[key] = result
        return result
