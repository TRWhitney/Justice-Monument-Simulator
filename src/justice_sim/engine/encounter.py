"""Encounter model implementations and harbinger injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from justice_sim.engine.effects import resolve_probability
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import EncounterModifier, GameState
from justice_sim.util import expr as expr_util


class EncounterModel:
    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        raise NotImplementedError

    def eligible_offers(self, state: GameState, data: JusticeData) -> list[str]:
        raise NotImplementedError

    def update_from_log(
        self, event: Mapping[str, str]
    ) -> None:  # pragma: no cover - optional
        return None


@dataclass
class UniformEncounterModel(EncounterModel):
    def eligible_offers(self, state: GameState, data: JusticeData) -> list[str]:
        offers = []
        for offer in data.offers:
            if _is_offer_eligible(offer, state, data):
                offers.append(offer.id)
        return offers

    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        offers = self.eligible_offers(state, data)
        if not offers:
            raise ValueError("No eligible offers")
        return rng.choice(offers)


@dataclass
class WeightedEncounterModel(EncounterModel):
    npc_weights: Mapping[str, float] = field(default_factory=dict)
    offer_weights: Mapping[str, float] = field(default_factory=dict)

    def eligible_offers(self, state: GameState, data: JusticeData) -> list[str]:
        return [
            offer.id for offer in data.offers if _is_offer_eligible(offer, state, data)
        ]

    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        offers = self.eligible_offers(state, data)
        choices: list[tuple[str, float]] = []
        for offer_id in offers:
            offer = data.offers_by_id[offer_id]
            weight = self.npc_weights.get(offer.npc_id, 1.0) * self.offer_weights.get(
                offer_id, 1.0
            )
            weight = _apply_modifiers(weight, offer, state.encounter_modifiers)
            if weight > 0:
                choices.append((offer_id, weight))
        if not choices:
            raise ValueError("No eligible offers with positive weight")
        return rng.weighted_choice(choices)


@dataclass
class LearnedEncounterModel(EncounterModel):
    priors: Mapping[str, float] = field(default_factory=dict)
    counts: Mapping[str, float] = field(default_factory=dict)

    def eligible_offers(self, state: GameState, data: JusticeData) -> list[str]:
        return [
            offer.id for offer in data.offers if _is_offer_eligible(offer, state, data)
        ]

    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        offers = self.eligible_offers(state, data)
        choices: list[tuple[str, float]] = []
        for offer_id in offers:
            prior = self.priors.get(offer_id, 1.0)
            count = self.counts.get(offer_id, 0.0)
            offer = data.offers_by_id[offer_id]
            weight = (prior + count) * _apply_modifiers(
                1.0, offer, state.encounter_modifiers
            )
            if weight > 0:
                choices.append((offer_id, weight))
        if not choices:
            raise ValueError("No eligible offers with positive weight")
        return rng.weighted_choice(choices)

    def update_from_log(self, event: Mapping[str, str]) -> None:
        offer_id = event.get("offer_id")
        if not offer_id:
            return
        counts = dict(self.counts)
        counts[offer_id] = counts.get(offer_id, 0.0) + 1.0
        self.counts = counts

    def export_priors(self) -> dict[str, float]:
        return dict(self.counts)

    def import_priors(self, priors: Mapping[str, float]) -> None:
        self.counts = dict(priors)


def select_encounter(
    state: GameState, data: JusticeData, encounter_model: EncounterModel, rng: Rng
) -> str:
    forced_offer = _forced_encounter_for_case(state)
    if forced_offer:
        return forced_offer

    harbinger_rule = data.special_rules.harbinger
    if state.case_index % harbinger_rule.cadence_modulus == 0:
        grateful_rule = data.special_rules.gratefulbinger
        if grateful_rule:
            probability = _evaluate_gratefulbinger_probability(state, data)
            if rng.random() <= probability:
                return grateful_rule.offer_id
        return harbinger_rule.offer_id

    return encounter_model.sample_encounter(state, data, rng)


def consume_forced_encounter(state: GameState, offer_id: str) -> GameState:
    from dataclasses import replace

    remaining = []
    consumed = False
    for forced in state.forced_encounters:
        if (
            not consumed
            and forced.offer_id == offer_id
            and forced.trigger_case_index == state.case_index
        ):
            if forced.once:
                consumed = True
                continue
        remaining.append(forced)
    if consumed:
        return replace(state, forced_encounters=tuple(remaining))
    return state


def _forced_encounter_for_case(state: GameState) -> str | None:
    for forced in state.forced_encounters:
        if forced.trigger_case_index == state.case_index:
            return forced.offer_id
    return None


def _evaluate_gratefulbinger_probability(state: GameState, data: JusticeData) -> float:
    rule = data.special_rules.gratefulbinger
    if not rule:
        return 0.0
    return resolve_probability(
        {"expr": rule.replace_harbinger_probability_expr, "format": rule.format},
        state,
        data,
    )


def _apply_modifiers(
    weight: float, offer: OfferSpec, modifiers: tuple[EncounterModifier, ...]
) -> float:
    adjusted = weight
    for modifier in modifiers:
        npc_weights = modifier.npc_weights or {}
        offer_weights = modifier.offer_weights or {}
        if modifier.mode == "set":
            if offer.npc_id in npc_weights:
                adjusted = npc_weights[offer.npc_id]
            if offer.id in offer_weights:
                adjusted = offer_weights[offer.id]
        else:
            if offer.npc_id in npc_weights:
                adjusted *= npc_weights[offer.npc_id]
            if offer.id in offer_weights:
                adjusted *= offer_weights[offer.id]
    return adjusted


def _is_offer_eligible(offer: OfferSpec, state: GameState, data: JusticeData) -> bool:
    if offer.id == data.special_rules.harbinger.offer_id:
        return False
    if (
        data.special_rules.gratefulbinger
        and offer.id == data.special_rules.gratefulbinger.offer_id
    ):
        return False
    if not offer.conditions:
        return True
    for predicate in offer.conditions:
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
            if not expr_util.evaluate_predicate(predicate, ctx):
                return False
    return True
