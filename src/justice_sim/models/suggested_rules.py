"""Suggested rule biases and constraints for planner recommendations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ActionBias:
    action: str
    amount: float
    when: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True)
class ActionConstraint:
    action: str
    mode: str
    when: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True)
class SuggestedRule:
    id: str
    offer_ids: tuple[str, ...]
    biases: tuple[ActionBias, ...]
    constraints: tuple[ActionConstraint, ...]
    notes: str | None = None


@dataclass(frozen=True)
class SuggestedRules:
    version: str
    rules: tuple[SuggestedRule, ...]
    metadata: Mapping[str, Any] | None = None
    biases_by_offer: Mapping[str, tuple[ActionBias, ...]] = field(default_factory=dict)
    constraints_by_offer: Mapping[str, tuple[ActionConstraint, ...]] = field(
        default_factory=dict
    )

    @staticmethod
    def empty() -> "SuggestedRules":
        return SuggestedRules(version="suggested_rules", rules=())

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "SuggestedRules":
        rules = tuple(_parse_rule(item) for item in payload.get("rules", []) or [])
        biases_by_offer: dict[str, list[ActionBias]] = {}
        constraints_by_offer: dict[str, list[ActionConstraint]] = {}
        for rule in rules:
            for offer_id in rule.offer_ids:
                biases_by_offer.setdefault(offer_id, []).extend(rule.biases)
                constraints_by_offer.setdefault(offer_id, []).extend(rule.constraints)
        return SuggestedRules(
            version=str(payload.get("version", "")),
            rules=rules,
            metadata=payload.get("metadata"),
            biases_by_offer={
                offer_id: tuple(biases) for offer_id, biases in biases_by_offer.items()
            },
            constraints_by_offer={
                offer_id: tuple(constraints)
                for offer_id, constraints in constraints_by_offer.items()
            },
        )

    def biases_for_offer(self, offer_id: str) -> tuple[ActionBias, ...]:
        return self.biases_by_offer.get(offer_id, ())

    def constraints_for_offer(self, offer_id: str) -> tuple[ActionConstraint, ...]:
        return self.constraints_by_offer.get(offer_id, ())


def _parse_rule(item: Mapping[str, Any]) -> SuggestedRule:
    rule_id = str(item.get("id", ""))
    offer_ids = tuple(str(value) for value in item.get("offer_ids", []) or [])
    biases = tuple(_parse_bias(rule_id, bias) for bias in item.get("biases", []) or [])
    constraints = tuple(
        _parse_constraint(rule_id, constraint)
        for constraint in item.get("constraints", []) or []
    )
    return SuggestedRule(
        id=rule_id,
        offer_ids=offer_ids,
        biases=biases,
        constraints=constraints,
        notes=item.get("notes"),
    )


def _parse_bias(rule_id: str, payload: Mapping[str, Any]) -> ActionBias:
    return ActionBias(
        action=str(payload.get("action")),
        amount=float(payload.get("amount", 0.0)),
        when=payload.get("when"),
        rule_id=rule_id,
    )


def _parse_constraint(rule_id: str, payload: Mapping[str, Any]) -> ActionConstraint:
    return ActionConstraint(
        action=str(payload.get("action")),
        mode=str(payload.get("mode")),
        when=payload.get("when"),
        rule_id=rule_id,
    )
