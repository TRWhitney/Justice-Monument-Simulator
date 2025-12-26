"""Shared offer search for CLI/GUI."""

from __future__ import annotations

from dataclasses import dataclass

from justice_sim.models.offer import JusticeData, OfferSpec
from justice_sim.models.state import GameState
from justice_sim.util.render import summarize_offer


@dataclass(frozen=True)
class OfferSearchResult:
    offer: OfferSpec
    npc_name: str
    approve_summary: str
    reject_summary: str
    dismiss_summary: str | None


def parse_search_query(query: str) -> tuple[str | None, list[str], list[str]]:
    tokens = [token for token in query.lower().split() if token]
    npc_query = None
    terms: list[str] = []
    effect_terms: list[str] = []
    for token in tokens:
        if token.startswith("#") and len(token) > 1 and npc_query is None:
            npc_query = token[1:]
        elif token.startswith("$") and len(token) > 1:
            effect_terms.append(token[1:])
        else:
            terms.append(token)
    return npc_query, terms, effect_terms


def search_offers(
    query: str, data: JusticeData, state: GameState
) -> list[OfferSearchResult]:
    query = query.strip()
    npc_query, terms, effect_terms = (
        parse_search_query(query) if query else (None, [], [])
    )
    results = []
    for offer in data.offers:
        npc = data.npcs_by_id.get(offer.npc_id)
        npc_name = npc.name if npc else offer.npc_id
        if npc_query and npc_query not in npc_name.lower():
            continue
        approve_summary, reject_summary, dismiss_summary = summarize_offer(
            offer, state, data
        )
        haystack = " ".join(
            filter(
                None,
                [
                    npc_name,
                    offer.title,
                    offer.text,
                    approve_summary,
                    reject_summary,
                    dismiss_summary or "",
                ],
            )
        ).lower()
        if terms and not _match_terms(terms, haystack):
            continue
        effect_haystack = " ".join(
            filter(None, [approve_summary, reject_summary])
        ).lower()
        if effect_terms and not _match_terms(effect_terms, effect_haystack):
            continue
        results.append(
            OfferSearchResult(
                offer=offer,
                npc_name=npc_name,
                approve_summary=approve_summary,
                reject_summary=reject_summary,
                dismiss_summary=dismiss_summary,
            )
        )
    return results


def _match_terms(terms: list[str], haystack: str) -> bool:
    return all(term in haystack for term in terms)
