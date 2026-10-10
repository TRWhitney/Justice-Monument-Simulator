"""Exact safety reuse for deterministic client Harbinger pools."""

from __future__ import annotations

import ast
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from functools import lru_cache
import operator

from justice_sim.engine.effects import outcome_additive_resource_cost
from justice_sim.engine.encounter import (
    _evaluate_gratefulbinger_probability,
    _mix_distribution,
    _pending_labels,
    eligible_harbinger_offers,
)
from justice_sim.engine.health import _probe_resources
from justice_sim.engine.reducer import _predicate_allows
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import GameState
from justice_sim.util.dependencies import referenced_counter_names


_REGION_RESOURCES = ("coins", "pop", "dismissals", "retirement_chests")


def _condition_boundaries(
    offers: tuple[OfferSpec, ...],
) -> dict[str, set[float]] | None:
    """Only direct resource/literal comparisons can use payment regions.

    Other state fields stay exact in the key. Reject an arithmetic expression,
    a function argument or a cross-resource comparison involving a binned value.
    """
    boundaries: dict[str, set[float]] = {name: set() for name in _REGION_RESOURCES}
    boundaries["dismissals"].add(0.0)
    for offer in offers:
        for predicate in offer.conditions:
            if not isinstance(predicate, str):
                continue
            try:
                tree = ast.parse(predicate, mode="eval")
            except SyntaxError:
                return None
            parents = {
                child: node
                for node in ast.walk(tree)
                for child in ast.iter_child_nodes(node)
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Name) or node.id not in boundaries:
                    continue
                parent = parents.get(node)
                if not isinstance(parent, ast.Compare) or len(parent.ops) != 1:
                    return None
                other = parent.comparators[0] if parent.left is node else parent.left
                try:
                    value = ast.literal_eval(other)
                except (ValueError, TypeError):
                    return None
                if not isinstance(value, (int, float)) or not isfinite(value):
                    return None
                boundaries[node.id].add(float(value))
    return boundaries


_COMPARISONS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _condition_reads(
    offers: tuple[OfferSpec, ...],
) -> tuple[set[str], dict[str, tuple | None]]:
    predicates = tuple(
        p for offer in offers for p in offer.conditions if isinstance(p, str)
    )
    counters: dict[str, list[tuple] | None] = {
        name: [] for name in referenced_counter_names(predicates)
    }
    names = set()
    for predicate in predicates:
        tree = ast.parse(predicate, mode="eval")
        parents = {
            child: node
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }
        names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "counters"
            ):
                continue
            comparisons = counters[node.attr]
            if comparisons is None:
                continue
            parent = parents.get(node)
            if isinstance(parent, ast.Compare) and len(parent.ops) == 1:
                other = parent.comparators[0] if parent.left is node else parent.left
                try:
                    literal = ast.literal_eval(other)
                except (ValueError, TypeError):
                    literal = None
                if (
                    isinstance(literal, (int, float))
                    and isfinite(literal)
                    and type(parent.ops[0]) in _COMPARISONS
                ):
                    comparisons.append(
                        (
                            _COMPARISONS[type(parent.ops[0])],
                            literal,
                            parent.left is node,
                        )
                    )
                    continue
            counters[node.attr] = None
    return names, {
        name: tuple(values) if values else None for name, values in counters.items()
    }


@lru_cache(maxsize=1024)
def _case_only_predicate(predicate: str) -> bool:
    """Prove that a trigger's guard cannot change during arrival or action."""
    try:
        tree = ast.parse(predicate, mode="eval")
    except SyntaxError:
        return False
    allowed = (
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.UnaryOp,
        ast.Not,
        ast.UAdd,
        ast.USub,
        ast.BinOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Compare,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.Gt,
        ast.GtE,
        ast.Constant,
        ast.Name,
        ast.Load,
    )
    return all(
        isinstance(node, allowed)
        and (not isinstance(node, ast.Name) or node.id == "case_index")
        and (not isinstance(node, ast.Constant) or isinstance(node.value, (int, float)))
        for node in ast.walk(tree)
    )


@dataclass(frozen=True)
class _PoolSafety:
    base: tuple[tuple[str, float], ...]
    unsafe: frozenset[str]


class RiskPoolCache:
    """Reuse pool safety, keeping current replacement probabilities live.

    Misses use the encounter selector and reducer health probes. The proof covers
    case-only immediate operations with no resource-changing arrivals. Matching
    contracts, due events, requirements and applicable overrides use full risk.
    """

    def __init__(self, data: JusticeData, max_entries: int = 10000) -> None:
        self.data = data
        self.max_entries = max_entries
        rule = data.special_rules.harbinger
        ids = (*rule.offer_pool, rule.offer_id, *rule.priority_offers)
        grateful = data.special_rules.gratefulbinger
        if grateful:
            ids += (grateful.offer_id,)
        self.offers = tuple(
            data.offers_by_id[key]
            for key in dict.fromkeys(ids)
            if key in data.offers_by_id
        )
        self.offer_ids = frozenset(offer.id for offer in self.offers)
        self.npc_ids = frozenset(offer.npc_id for offer in self.offers)
        self.boundaries = _condition_boundaries(self.offers)
        self.condition_names, self.counter_reads = (
            _condition_reads(self.offers)
            if self.boundaries is not None
            else (set(), {})
        )
        if (
            not data.special_rules.client_encounters
            or not self.offers
            or any(key not in data.offers_by_id for key in ids)
            or any(
                _probe_resources(data, offer, action) is None
                for offer in self.offers
                for action in offer.actions_available
            )
            or any(
                effect.type not in {"set_counter", "increment_counter", "clear_counter"}
                for offer in self.offers
                for effect in offer.arrival_effects
            )
        ):
            self.boundaries = None
        self._case_boundaries: OrderedDict[int, tuple[tuple[float, ...], ...]] = (
            OrderedDict()
        )
        self._cache: OrderedDict[tuple, _PoolSafety] = OrderedDict()
        self._inactive_guards: OrderedDict[tuple[int, str], bool] = OrderedDict()

    def _inactive(self, predicate: object, state: GameState) -> bool:
        if not isinstance(predicate, str) or not _case_only_predicate(predicate):
            return False
        key = state.case_index, predicate
        cached = self._inactive_guards.get(key)
        if cached is None:
            cached = not _predicate_allows(predicate, state, self.data)
            if len(self._inactive_guards) >= self.max_entries:
                self._inactive_guards.popitem(last=False)
            self._inactive_guards[key] = cached
        return cached

    def _supports_state(self, state: GameState) -> bool:
        modulus = self.data.special_rules.harbinger.cadence_modulus
        return (
            self.boundaries is not None
            and self.max_entries > 0
            and modulus > 0
            and state.case_index % modulus == 0
            and not state.required_action
            and not state.required_action_penalty_effects
            and not any(
                event.trigger_case_index == state.case_index + 1
                for event in state.scheduled_events
            )
            and not any(
                forced.trigger_case_index == state.case_index
                for forced in state.forced_encounters
            )
            and not any(
                override.allow_harbinger
                and override.label
                not in {"bean_loan_return", "chest_magnetizer", "bean_secret"}
                for override in state.encounter_overrides
            )
            and not any(
                (not trigger.offer_id or trigger.offer_id in self.offer_ids)
                and (not trigger.npc_id or trigger.npc_id in self.npc_ids)
                and not self._inactive(trigger.when, state)
                for trigger in (*state.encounter_triggers, *state.action_triggers)
            )
            and all(
                isfinite(getattr(state, resource))
                for resource in (*_REGION_RESOURCES, "mh")
            )
        )

    def _cuts(self, state: GameState) -> tuple[tuple[float, ...], ...]:
        cached = self._case_boundaries.get(state.case_index)
        if cached is not None:
            return cached
        assert self.boundaries is not None
        boundaries = {name: set(values) for name, values in self.boundaries.items()}
        for offer in self.offers:
            resource = offer.payment_resource
            if "approve" in offer.actions_available and resource in boundaries:
                boundaries[resource].add(
                    outcome_additive_resource_cost(
                        state, offer.approve, resource, self.data
                    )
                )
        base = self.data.offers_by_id[self.data.special_rules.harbinger.offer_id]
        if "approve" in base.actions_available:
            # The base unpaid penalty reads coins even with a different declared
            # payment resource. It has a separate reducer payment boundary.
            boundaries["coins"].add(
                outcome_additive_resource_cost(state, base.approve, "coins", self.data)
            )
        cuts = tuple(tuple(sorted(boundaries[name])) for name in _REGION_RESOURCES)
        if len(self._case_boundaries) >= self.max_entries:
            self._case_boundaries.popitem(last=False)
        self._case_boundaries[state.case_index] = cuts
        return cuts

    def risk(
        self,
        state: GameState,
        health_probe: Callable[[GameState, OfferSpec, str], bool],
    ) -> float | None:
        if not self._supports_state(state):
            return None
        cuts = self._cuts(state)
        regions = tuple(
            (bisect_left(boundaries, value), bisect_right(boundaries, value))
            for resource, boundaries in zip(_REGION_RESOURCES, cuts)
            for value in (getattr(state, resource),)
        )
        key = (
            state.case_index,
            regions,
            state.mh,
            state.ended,
            tuple(sorted(state.flags))
            if self.condition_names & {"flags", "has_flag"}
            else (),
            tuple(sorted(state.statuses))
            if self.condition_names & {"statuses", "has_status"}
            else tuple(
                name in state.statuses
                for name in (
                    "cannot_approve",
                    "cannot_reject",
                    "cannot_dismiss",
                    "cannot_dismiss_harbinger",
                )
            ),
            tuple(sorted(_pending_labels(state)))
            if "has_pending" in self.condition_names
            else (),
            tuple(
                tuple(
                    compare(value, literal) if left else compare(literal, value)
                    for compare, literal, left in comparisons
                )
                if comparisons is not None
                else value
                for name, comparisons in self.counter_reads.items()
                for value in (float(state.counters.get(name, 0)),)
            ),
            state.resource_floors.get("mh"),
        )
        safety = self._cache.get(key)
        if safety is None:
            pool = eligible_harbinger_offers(state, self.data)
            base = {offer_id: 1 / len(pool) for offer_id in pool}
            candidates = list(base)
            grateful = self.data.special_rules.gratefulbinger
            if grateful and grateful.offer_id not in candidates:
                candidates.append(grateful.offer_id)
            unsafe = set()
            for offer_id in candidates:
                offer = self.data.offers_by_id[offer_id]
                actions = offer.actions_available
                if "dismiss" in actions:
                    actions = (
                        "dismiss",
                        *(action for action in actions if action != "dismiss"),
                    )
                if not any(health_probe(state, offer, action) for action in actions):
                    unsafe.add(offer_id)
            safety = _PoolSafety(tuple(base.items()), frozenset(unsafe))
            if len(self._cache) >= self.max_entries:
                self._cache.popitem(last=False)
            self._cache[key] = safety
        # Preserve the original mix and ordered additions bit for bit. Factoring
        # a summed risk by (1-p) would change floating-point rounding.
        distribution = dict(safety.base)
        grateful = self.data.special_rules.gratefulbinger
        if grateful:
            distribution = _mix_distribution(
                distribution,
                {grateful.offer_id: 1},
                _evaluate_gratefulbinger_probability(state, self.data),
            )
        risk = 0.0
        for offer_id, probability in distribution.items():
            if offer_id in safety.unsafe:
                risk += probability
        return risk
