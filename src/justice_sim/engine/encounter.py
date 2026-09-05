"""Encounter model implementations and harbinger injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from justice_sim.engine.effects import resolve_probability
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import EncounterModifier, EncounterOverride, GameState
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
        return _eligible_regular_offer_ids(self, state, data)

    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        offers = self.eligible_offers(state, data)
        if not offers:
            raise ValueError("No eligible offers")
        if all(data.offers_by_id[key].encounter_weight == 1 for key in offers):
            return rng.choice(offers)
        return rng.weighted_choice(
            [(key, data.offers_by_id[key].encounter_weight) for key in offers]
        )


@dataclass
class WeightedEncounterModel(EncounterModel):
    npc_weights: Mapping[str, float] = field(default_factory=dict)
    offer_weights: Mapping[str, float] = field(default_factory=dict)

    def eligible_offers(self, state: GameState, data: JusticeData) -> list[str]:
        return _eligible_regular_offer_ids(self, state, data)

    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        offers = self.eligible_offers(state, data)
        choices: list[tuple[str, float]] = []
        for offer_id in offers:
            offer = data.offers_by_id[offer_id]
            weight = (
                offer.encounter_weight
                * self.npc_weights.get(offer.npc_id, 1.0)
                * self.offer_weights.get(offer_id, 1.0)
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
        return _eligible_regular_offer_ids(self, state, data)

    def sample_encounter(self, state: GameState, data: JusticeData, rng: Rng) -> str:
        offers = self.eligible_offers(state, data)
        choices: list[tuple[str, float]] = []
        for offer_id in offers:
            prior = self.priors.get(offer_id, 1.0)
            count = self.counts.get(offer_id, 0.0)
            offer = data.offers_by_id[offer_id]
            weight = (prior * offer.encounter_weight + count) * _apply_modifiers(
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

    if data.special_rules.client_encounters:
        return rng.weighted_choice(
            list(client_encounter_probabilities(state, data, encounter_model).items())
        )

    harbinger_rule = data.special_rules.harbinger
    harbinger_case = state.case_index % harbinger_rule.cadence_modulus == 0

    override_offer = _override_encounter_for_case(state, data, rng, harbinger_case)
    if override_offer:
        return override_offer

    if harbinger_case:
        grateful_rule = data.special_rules.gratefulbinger
        if grateful_rule:
            probability = _evaluate_gratefulbinger_probability(state, data)
            if rng.random() < probability:
                return grateful_rule.offer_id
        return _select_harbinger_offer(state, data, rng)

    return encounter_model.sample_encounter(state, data, rng)


def possible_encounter_offers(
    state: GameState, data: JusticeData, encounter_model: EncounterModel
) -> list[str]:
    if state.ended:
        return []
    forced_offer = _forced_encounter_for_case(state)
    if forced_offer:
        return [forced_offer]

    if data.special_rules.client_encounters:
        return sorted(client_encounter_probabilities(state, data, encounter_model))

    harbinger_rule = data.special_rules.harbinger
    harbinger_case = state.case_index % harbinger_rule.cadence_modulus == 0
    override_possible, deterministic_override = _possible_override_encounters(
        state, data, harbinger_case
    )
    possible = set(override_possible)
    if deterministic_override:
        return sorted(possible)

    if harbinger_case:
        grateful_rule = data.special_rules.gratefulbinger
        if grateful_rule:
            probability = _evaluate_gratefulbinger_probability(state, data)
            if probability > 0:
                possible.add(grateful_rule.offer_id)
        possible.update(eligible_harbinger_offers(state, data))
        return sorted(possible)

    possible.update(encounter_model.eligible_offers(state, data))
    return sorted(possible)


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


def _override_encounter_for_case(
    state: GameState,
    data: JusticeData,
    rng: Rng,
    harbinger_case: bool,
) -> str | None:
    ordered = sorted(
        enumerate(state.encounter_overrides),
        key=lambda item: (-item[1].priority, item[0]),
    )
    for _, override in ordered:
        if harbinger_case and not override.allow_harbinger:
            continue
        if override.probability is not None:
            probability = resolve_probability(override.probability, state, data)
            if rng.random() >= probability:
                continue
        if override.offer_id:
            offer = data.offers_by_id.get(override.offer_id)
            if offer and _is_offer_eligible(offer, state, data):
                return override.offer_id
            continue
        if override.npc_id:
            offers = [
                offer.id
                for offer in data.offers
                if offer.npc_id == override.npc_id
                and _is_offer_eligible(offer, state, data)
            ]
            if offers:
                return rng.choice(offers)
    return None


def _possible_override_encounters(
    state: GameState, data: JusticeData, harbinger_case: bool
) -> tuple[set[str], bool]:
    possible: set[str] = set()
    ordered = sorted(
        enumerate(state.encounter_overrides),
        key=lambda item: (-item[1].priority, item[0]),
    )
    for _, override in ordered:
        if harbinger_case and not override.allow_harbinger:
            continue
        candidates = _override_candidate_offer_ids(override, state, data)
        if not candidates:
            continue
        if override.probability is None:
            possible.update(candidates)
            return possible, True
        probability = resolve_probability(override.probability, state, data)
        if probability <= 0:
            continue
        possible.update(candidates)
        if probability >= 1:
            return possible, True
    return possible, False


def _override_candidate_offer_ids(
    override: EncounterOverride, state: GameState, data: JusticeData
) -> list[str]:
    if override.offer_id:
        offer = data.offers_by_id.get(override.offer_id)
        if offer and _is_offer_eligible(offer, state, data):
            return [override.offer_id]
        return []
    if not override.npc_id:
        return []
    return [
        offer.id
        for offer in data.offers
        if offer.npc_id == override.npc_id and _is_offer_eligible(offer, state, data)
    ]


def _evaluate_gratefulbinger_probability(state: GameState, data: JusticeData) -> float:
    rule = data.special_rules.gratefulbinger
    if not rule or state.pop < rule.minimum_pop:
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
    return _is_offer_eligible_internal(offer, state, data, allow_harbinger=False)


def _eligible_regular_offer_ids(
    encounter_model: EncounterModel, state: GameState, data: JusticeData
) -> list[str]:
    cached = getattr(encounter_model, "_regular_offer_candidates_cache", None)
    if cached is None or cached[0] is not data:
        excluded_offer_ids = _harbinger_offer_ids(data)
        if data.special_rules.gratefulbinger:
            excluded_offer_ids.add(data.special_rules.gratefulbinger.offer_id)
        candidates = tuple(
            offer for offer in data.offers if offer.id not in excluded_offer_ids
        )
        cached = (data, candidates)
        setattr(encounter_model, "_regular_offer_candidates_cache", cached)
    candidates = cached[1]
    return [
        offer.id
        for offer in candidates
        if offer.encounter_weight > 0
        and (not offer.conditions or _offer_conditions_allow(offer, state))
    ]


def _is_offer_eligible_internal(
    offer: OfferSpec,
    state: GameState,
    data: JusticeData,
    *,
    allow_harbinger: bool,
) -> bool:
    if not allow_harbinger:
        if offer.id in _harbinger_offer_ids(data):
            return False
        if (
            data.special_rules.gratefulbinger
            and offer.id == data.special_rules.gratefulbinger.offer_id
        ):
            return False
    return _offer_conditions_allow(offer, state)


def _offer_conditions_allow(offer: OfferSpec, state: GameState) -> bool:
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
                pending=_pending_labels(state),
            )
            if not expr_util.evaluate_predicate(predicate, ctx):
                return False
    return True


def _harbinger_offer_ids(data: JusticeData) -> set[str]:
    rule = data.special_rules.harbinger
    ids = set(rule.offer_pool)
    if rule.offer_id:
        ids.add(rule.offer_id)
    return ids


def _harbinger_offer_pool(data: JusticeData) -> list[str]:
    rule = data.special_rules.harbinger
    if rule.offer_pool:
        return list(rule.offer_pool)
    return [rule.offer_id]


def _select_harbinger_offer(state: GameState, data: JusticeData, rng: Rng) -> str:
    return rng.choice(eligible_harbinger_offers(state, data))


def eligible_harbinger_offers(state: GameState, data: JusticeData) -> list[str]:
    for offer_id in data.special_rules.harbinger.priority_offers:
        offer = data.offers_by_id.get(offer_id)
        if offer and _is_offer_eligible_internal(
            offer, state, data, allow_harbinger=True
        ):
            return [offer_id]
    pool = _harbinger_offer_pool(data)
    eligible: list[str] = []
    for offer_id in pool:
        offer = data.offers_by_id.get(offer_id)
        if offer and _is_offer_eligible_internal(
            offer, state, data, allow_harbinger=True
        ):
            eligible.append(offer_id)
    if not eligible and data.special_rules.harbinger.offer_id:
        return [data.special_rules.harbinger.offer_id]
    return eligible


def _pending_labels(state: GameState) -> set[str]:
    return {
        item.label
        for items in (
            state.scheduled_events,
            state.encounter_triggers,
            state.action_triggers,
            state.encounter_overrides,
        )
        for item in items
        if item.label
    }


def client_encounter_probabilities(
    state: GameState, data: JusticeData, model: EncounterModel
) -> dict[str, float]:
    """Integrate the client's row proposals and ordered replacements exactly.

    Merged, indistinguishable rows retain their multiplicity. Rejected loan
    proposals retain the base distribution, just as a client reroll does.
    Custom learned/weighted models remain usable for the ordinary proposal.
    """
    forced = _forced_encounter_for_case(state)
    if forced:
        return {forced: 1.0}
    harbinger_case = (
        state.case_index % data.special_rules.harbinger.cadence_modulus == 0
    )
    if harbinger_case:
        pool = eligible_harbinger_offers(state, data)
        distribution = {key: 1 / len(pool) for key in pool}
        grateful = data.special_rules.gratefulbinger
        if grateful:
            distribution = _mix_distribution(
                distribution,
                {grateful.offer_id: 1},
                _evaluate_gratefulbinger_probability(state, data),
            )
    else:
        weights = {}
        for key in model.eligible_offers(state, data):
            offer = data.offers_by_id[key]
            weight = offer.encounter_weight
            if isinstance(model, WeightedEncounterModel):
                weight *= model.npc_weights.get(
                    offer.npc_id, 1
                ) * model.offer_weights.get(key, 1)
                weight = _apply_modifiers(weight, offer, state.encounter_modifiers)
            elif isinstance(model, LearnedEncounterModel):
                weight = model.priors.get(key, 1) * weight + model.counts.get(key, 0)
                weight = _apply_modifiers(weight, offer, state.encounter_modifiers)
            if weight > 0:
                weights[key] = weight
        distribution = _normalize_weights(weights)
        if "bean_loan_payback" in _pending_labels(state):
            proposal = {}
            for row in (27, 28, 29):
                candidates = _client_row_offers(data, (row,))
                key = next(iter(candidates), None)
                if key and _is_offer_eligible(data.offers_by_id[key], state, data):
                    proposal[key] = proposal.get(key, 0) + 1 / 3
                else:
                    for base_key, probability in distribution.items():
                        proposal[base_key] = proposal.get(base_key, 0) + probability / 3
            distribution = _mix_distribution(distribution, proposal, 0.15)
        if state.case_index > 5 and state.case_index % 5 == 1:
            distribution = _mix_distribution(
                distribution, _client_row_offers(data, (21, 22)), 0.4
            )
        magnet = next(
            (o for o in state.encounter_overrides if o.label == "chest_magnetizer"),
            None,
        )
        if magnet:
            distribution = (
                _client_row_offers(data, (21, 22, 33, 37, 39, 52)) or distribution
            )
        elif state.counters.get("fizarre_drink_approves", 0) >= 3:
            distribution = _client_row_offers(data, (61,)) or distribution
    # Keep user/custom overrides, including their original priority semantics.
    overrides = sorted(
        enumerate(state.encounter_overrides),
        key=lambda item: (item[1].priority, -item[0]),
    )
    for _, override in overrides:
        if override.label in {"bean_loan_return", "chest_magnetizer", "bean_secret"}:
            continue
        if harbinger_case and not override.allow_harbinger:
            continue
        candidates = _override_candidate_offer_ids(override, state, data)
        if candidates:
            probability = (
                1
                if override.probability is None
                else resolve_probability(override.probability, state, data)
            )
            distribution = _mix_distribution(
                distribution,
                {key: 1 / len(candidates) for key in candidates},
                probability,
            )
    return distribution


def _client_row_offers(data: JusticeData, rows: tuple[int, ...]) -> dict[str, float]:
    weights = {
        offer.id: len(set(offer.client_rows).intersection(rows))
        for offer in data.offers
    }
    return _normalize_weights(
        {key: weight for key, weight in weights.items() if weight}
    )


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {key: weight / total for key, weight in weights.items()} if total else {}


def _mix_distribution(
    base: dict[str, float], replacement: dict[str, float], probability: float
) -> dict[str, float]:
    if not replacement:
        return base
    result = {key: value * (1 - probability) for key, value in base.items()}
    for key, value in replacement.items():
        result[key] = result.get(key, 0) + value * probability
    return {key: value for key, value in result.items() if value > 0}
