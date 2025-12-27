"""Shared offer search for CLI/GUI."""

from __future__ import annotations

from dataclasses import dataclass
import re

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


def normalize_npc_query(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return normalized.strip("_")


def npc_matches_query(npc_name: str, npc_id: str, npc_query: str) -> bool:
    if not npc_query:
        return True
    query_raw = npc_query.lower().strip()
    query_norm = normalize_npc_query(query_raw)
    npc_name_raw = npc_name.lower()
    npc_id_raw = npc_id.lower()
    npc_name_norm = normalize_npc_query(npc_name_raw)
    npc_id_norm = normalize_npc_query(npc_id_raw)
    if query_norm and (query_norm == npc_name_norm or query_norm == npc_id_norm):
        return True
    if query_raw and (query_raw in npc_name_raw or query_raw in npc_id_raw):
        return True
    if query_norm and (query_norm in npc_name_norm or query_norm in npc_id_norm):
        return True
    return False


def search_offers(
    query: str,
    data: JusticeData,
    state: GameState,
    *,
    eligible_offer_ids: set[str] | None = None,
) -> list[OfferSearchResult]:
    query = query.strip()
    npc_query, terms, effect_terms = (
        parse_search_query(query) if query else (None, [], [])
    )
    results = []
    for offer in data.offers:
        if eligible_offer_ids is not None and offer.id not in eligible_offer_ids:
            continue
        npc = data.npcs_by_id.get(offer.npc_id)
        npc_name = npc.name if npc else offer.npc_id
        if npc_query and not npc_matches_query(npc_name, offer.npc_id, npc_query):
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
