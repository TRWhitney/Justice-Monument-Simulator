"""Validation helpers for Justice data."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from justice_sim.models.offer import JusticeData
from justice_sim.util import expr as expr_util


class ValidationError(ValueError):
    """Raised when data validation fails."""


_SUPPORTED_EFFECT_TYPES = {
    "add_resource",
    "set_resource",
    "clamp_resource",
    "multiply_resource",
    "swap_resources",
    "add_flag",
    "remove_flag",
    "add_status",
    "remove_status",
    "set_resource_floor",
    "clear_resource_floor",
    "schedule_effects",
    "schedule_recurring_effects",
    "require_next_action",
    "add_action_trigger",
    "remove_action_trigger",
    "add_encounter_trigger",
    "remove_encounter_trigger",
    "add_encounter_override",
    "remove_encounter_override",
    "modify_encounter_weights",
    "end_run",
    "noop",
    "raw_effect",
    "random_range_resource",
    "random_exchange",
    "set_counter",
    "add_counter",
    "clear_counter",
}


def validate_data(data: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    npc_ids = [npc.get("id") for npc in data.get("npcs", [])]
    offer_ids = [offer.get("id") for offer in data.get("offers", [])]

    _report_duplicates("npc", npc_ids, errors)
    _report_duplicates("offer", offer_ids, errors)

    npc_id_set = {npc_id for npc_id in npc_ids if npc_id}

    for offer in data.get("offers", []):
        npc_id = offer.get("npc_id")
        if npc_id not in npc_id_set:
            errors.append(
                f"Offer '{offer.get('id')}' references unknown npc_id '{npc_id}'"
            )

        for predicate in offer.get("conditions", []) or []:
            _validate_predicate(predicate, offer.get("id"), errors)

        for outcome_key in ("approve", "reject", "dismiss"):
            outcome = offer.get(outcome_key)
            if not outcome:
                continue
            _validate_outcome(outcome, offer.get("id"), errors)

    return errors


def validate_suggested_rules(
    rules: Mapping[str, Any], *, offer_ids: Iterable[str] | None = None
) -> list[str]:
    errors: list[str] = []
    rule_ids = [rule.get("id") for rule in rules.get("rules", [])]
    _report_duplicates("suggested rule", rule_ids, errors)
    offer_id_set = set(offer_ids or [])

    for rule in rules.get("rules", []) or []:
        rule_id = rule.get("id")
        for offer_id in rule.get("offer_ids", []) or []:
            if offer_id_set and offer_id not in offer_id_set:
                errors.append(
                    f"Suggested rule '{rule_id}' references unknown offer_id '{offer_id}'"
                )
        for bias in rule.get("biases", []) or []:
            predicate = bias.get("when")
            if predicate is None:
                continue
            _validate_suggested_predicate(predicate, rule_id, errors)
        for constraint in rule.get("constraints", []) or []:
            predicate = constraint.get("when")
            if predicate is None:
                continue
            _validate_suggested_predicate(predicate, rule_id, errors)

    return errors


def _validate_suggested_predicate(
    predicate: Any, rule_id: str | None, errors: list[str]
) -> None:
    if isinstance(predicate, str):
        ctx = expr_util.build_predicate_context(
            case_index=1,
            coins=0,
            pop=0,
            mh=1,
            dismissals=0,
            retirement_chests=0,
            flags=set(),
            statuses=set(),
            counters={},
            extra_vars={
                "case_scale": 1,
                "harbinger_cost": 1,
                "harbinger_in": 1,
            },
        )
        try:
            expr_util.evaluate_predicate(predicate, ctx)
        except expr_util.ExprError as exc:
            errors.append(
                f"Suggested rule '{rule_id}' has malformed predicate '{predicate}': {exc}"
            )
        return
    if predicate is None:
        return
    errors.append(f"Suggested rule '{rule_id}' has unsupported predicate format")


def _report_duplicates(label: str, ids: Iterable[Any], errors: list[str]) -> None:
    seen: set[Any] = set()
    for item_id in ids:
        if not item_id:
            continue
        if item_id in seen:
            errors.append(f"duplicate {label} id '{item_id}'")
        seen.add(item_id)


def _validate_predicate(
    predicate: Any, offer_id: str | None, errors: list[str]
) -> None:
    if isinstance(predicate, str):
        error = expr_util.validate_predicate(predicate)
        if error:
            errors.append(
                f"Offer '{offer_id}' has malformed predicate '{predicate}': {error}"
            )
        return
    if predicate is None:
        return
    errors.append(f"Offer '{offer_id}' has unsupported predicate format")


def _validate_outcome(
    outcome: Mapping[str, Any], offer_id: str | None, errors: list[str]
) -> None:
    for effect in outcome.get("effects", []) or []:
        _validate_effect(effect, offer_id, errors)
    random_spec = outcome.get("random")
    if not random_spec:
        return
    if random_spec.get("type") == "bernoulli":
        for effect in random_spec.get("then", []) or []:
            _validate_effect(effect, offer_id, errors)
        for effect in random_spec.get("else", []) or []:
            _validate_effect(effect, offer_id, errors)
    elif random_spec.get("type") == "categorical":
        for choice in random_spec.get("choices", []) or []:
            for effect in choice.get("effects", []) or []:
                _validate_effect(effect, offer_id, errors)
    else:
        errors.append(
            f"Offer '{offer_id}' has unknown random spec type '{random_spec.get('type')}'"
        )


def _validate_effect(
    effect: Mapping[str, Any], offer_id: str | None, errors: list[str]
) -> None:
    effect_type = effect.get("type")
    if effect_type not in _SUPPORTED_EFFECT_TYPES:
        errors.append(f"Offer '{offer_id}' has unknown effect type '{effect_type}'")
    when = effect.get("when")
    if isinstance(when, str):
        error = expr_util.validate_predicate(when)
        if error:
            errors.append(
                f"Offer '{offer_id}' has malformed predicate '{when}': {error}"
            )


def build_minimal_data() -> JusticeData:
    data = {
        "version": "test",
        "defaults": {
            "debt_mode": "clamp_to_zero",
            "default_probability_format": "unit",
            "encounter_model_default": "uniform",
            "planner_defaults": {
                "horizon_cases": 5,
                "rollouts_per_action": 50,
                "adaptive_rollouts": False,
                "adaptive_rollouts_max": 100,
                "risk_preset": "balanced",
            },
        },
        "npcs": [
            {"id": "npc", "name": "NPC"},
            {"id": "the_harbinger", "name": "Harbinger"},
            {"id": "the_gratefulbinger", "name": "Grateful"},
        ],
        "offers": [
            {
                "id": "offer",
                "npc_id": "npc",
                "title": "Offer",
                "text": "Offer",
                "actions_available": ["approve", "reject"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            },
            {
                "id": "harbinger_offer",
                "npc_id": "the_harbinger",
                "title": "Harbinger",
                "text": "Pay",
                "actions_available": ["approve", "reject"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            },
            {
                "id": "grateful_offer",
                "npc_id": "the_gratefulbinger",
                "title": "Grateful",
                "text": "Thanks",
                "actions_available": ["approve", "reject"],
                "approve": {"effects": []},
                "reject": {"effects": []},
            },
        ],
        "special_rules": {
            "case_scale": {"mode": "expr", "expr": "ceil(case_index/5)"},
            "harbinger": {
                "offer_id": "harbinger_offer",
                "cadence_modulus": 5,
                "cost_expr": "ceil(case_index/5)",
                "on_unpaid_effects": [],
            },
            "gratefulbinger": {
                "offer_id": "grateful_offer",
                "replace_harbinger_probability_expr": "(40*pop)/(pop+20)",
                "format": "percent",
            },
        },
    }
    return JusticeData.from_dict(data)
