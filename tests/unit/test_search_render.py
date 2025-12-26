import pytest

from justice_sim.models.offer import EffectSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.util.render import summarize_outcome
from justice_sim.util.search import search_offers


@pytest.mark.unit
def test_search_by_npc_prefix(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("#npc one", data, state)
    assert results
    assert all(result.offer.npc_id == "npc1" for result in results)


@pytest.mark.unit
def test_search_empty_query_returns_all(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("", data, state)
    assert len(results) == len(data.offers)


@pytest.mark.unit
def test_search_full_text_matches_summary(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("coins", data, state)
    assert any(result.offer.id == "offer1" for result in results)


@pytest.mark.unit
def test_summary_includes_raw_effect_text(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    outcome = OutcomeSpec(
        effects=(EffectSpec(type="raw_effect", params={"raw": "special"}),),
    )
    summary = summarize_outcome(outcome, state, data)
    assert "special" in summary


@pytest.mark.unit
def test_search_allows_mixed_npc_and_terms(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("#npc one hello", data, state)
    assert results
    assert all(result.offer.npc_id == "npc1" for result in results)


@pytest.mark.unit
def test_summary_scales_by_case(data_factory):
    data = data_factory()
    state = GameState(
        case_index=6,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    outcome = OutcomeSpec(
        effects=(
            EffectSpec(
                type="add_resource",
                params={
                    "resource": "coins",
                    "amount": {"expr": "2", "scaled_by_case": True},
                },
            ),
        ),
    )
    summary = summarize_outcome(outcome, state, data)
    assert "+4 coins" in summary
    assert "*case" not in summary


@pytest.mark.unit
def test_search_effect_terms_only(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("$coins", data, state)
    offer_ids = {result.offer.id for result in results}
    assert "offer1" in offer_ids
    assert "offer2" in offer_ids
    assert "harbinger_offer" in offer_ids
    assert "grateful_offer" in offer_ids
    assert "timmy_offer" not in offer_ids


@pytest.mark.unit
def test_search_mixed_effect_and_free_terms(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("hello $coins", data, state)
    assert [result.offer.id for result in results] == ["offer1"]


@pytest.mark.unit
def test_search_npc_and_effect_terms(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    results = search_offers("#npc $pop", data, state)
    assert [result.offer.id for result in results] == ["offer1"]
