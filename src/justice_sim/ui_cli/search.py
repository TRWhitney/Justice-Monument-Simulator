"""CLI search wrapper."""

from __future__ import annotations

from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.util.search import OfferSearchResult, search_offers


def search(
    query: str,
    data: JusticeData,
    state: GameState,
    *,
    eligible_offer_ids: set[str] | None = None,
) -> list[OfferSearchResult]:
    return search_offers(query, data, state, eligible_offer_ids=eligible_offer_ids)
