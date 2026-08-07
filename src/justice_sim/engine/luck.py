"""Encounter luck ranking helpers."""

from __future__ import annotations

from dataclasses import dataclass

from justice_sim.engine.encounter import EncounterModel, possible_encounter_offers
from justice_sim.engine.reducer import ActionNotAllowed, apply_action
from justice_sim.engine.rng import Rng, RngState
from justice_sim.engine.scoring import UtilityWeights, utility
from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import GameState


@dataclass(frozen=True)
class EncounterLuck:
    rank: int
    total: int

    def to_dict(self) -> dict[str, int]:
        return {"rank": self.rank, "total": self.total}

    @staticmethod
    def from_dict(payload: dict[str, object]) -> "EncounterLuck":
        return EncounterLuck(
            rank=int(payload.get("rank", 0)),
            total=int(payload.get("total", 0)),
        )


def rank_encounter_offer(
    state: GameState,
    offer_id: str,
    data: JusticeData,
    encounter_model: EncounterModel,
    *,
    weights: UtilityWeights | None = None,
    rng_state: RngState | None = None,
) -> EncounterLuck | None:
    rankings = encounter_offer_rankings(
        state,
        data,
        encounter_model,
        weights=weights,
        rng_state=rng_state,
    )
    return rankings.get(offer_id)


def encounter_offer_rankings(
    state: GameState,
    data: JusticeData,
    encounter_model: EncounterModel,
    *,
    weights: UtilityWeights | None = None,
    rng_state: RngState | None = None,
    candidate_offer_ids: set[str] | None = None,
) -> dict[str, EncounterLuck]:
    if candidate_offer_ids is None:
        possible_offer_ids = possible_encounter_offers(state, data, encounter_model)
    else:
        possible_offer_ids = sorted(candidate_offer_ids)
    if not possible_offer_ids:
        return {}

    weights = weights or UtilityWeights()
    scored: list[tuple[str, float]] = []
    for possible_offer_id in possible_offer_ids:
        offer = data.offers_by_id.get(possible_offer_id)
        if offer is None:
            continue
        score = _best_action_score(state, offer, data, weights, rng_state)
        if score is None:
            continue
        scored.append((possible_offer_id, score))
    if not scored:
        return {}

    scored.sort(key=lambda item: (-item[1], item[0]))
    total = len(scored)
    rankings: dict[str, EncounterLuck] = {}
    for index, (ranked_offer_id, _score) in enumerate(scored, start=1):
        rankings[ranked_offer_id] = EncounterLuck(rank=index, total=total)
    return rankings


def encounter_luck_color(rank: int, total: int) -> str:
    if total <= 1:
        ratio = 1.0
    else:
        clamped_rank = max(1, min(rank, total))
        ratio = (total - clamped_rank) / (total - 1)
    red = int(round(191 - (119 * ratio)))
    green = int(round(58 + (134 * ratio)))
    blue = int(round(48 + (32 * ratio)))
    return f"#{red:02x}{green:02x}{blue:02x}"


def _best_action_score(
    state: GameState,
    offer: OfferSpec,
    data: JusticeData,
    weights: UtilityWeights,
    rng_state: RngState | None,
) -> float | None:
    best_score: float | None = None
    for action in offer.actions_available:
        trial_rng = _trial_rng(rng_state)
        try:
            next_state, _ = apply_action(state, offer, action, data, trial_rng)
        except ActionNotAllowed:
            continue
        score = utility(next_state, data, weights)
        if best_score is None or score > best_score:
            best_score = score
    return best_score


def _trial_rng(rng_state: RngState | None) -> Rng:
    if rng_state is not None:
        return Rng.from_state(rng_state)
    return Rng(0)
