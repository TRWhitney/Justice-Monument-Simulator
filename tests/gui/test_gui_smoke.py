import os

import pytest

from justice_sim.config import load_builtin_data
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow
from justice_sim.models.state import GameState
from justice_sim.ui_qt.widgets.offer_card import OfferCard
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget
from justice_sim.util.render import summarize_offer
from justice_sim.util.search import OfferSearchResult


@pytest.mark.gui
def test_main_window_instantiates():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = load_builtin_data()
    window = MainWindow(data)
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    offer = data.offers[0]
    approve, reject, dismiss = summarize_offer(offer, state, data)
    result = OfferSearchResult(
        offer=offer,
        npc_name=data.npcs_by_id[offer.npc_id].name,
        approve_summary=approve,
        reject_summary=reject,
        dismiss_summary=dismiss,
    )
    _card = OfferCard(data, result, state)
    search_widget = OfferSearchWidget(data, state)
    search_widget.search_input.setText(offer.title.split()[0])
    search_widget.results_list.setCurrentRow(0)
    search_widget._on_selection()
    assert window is not None
    window.close()
    app.quit()


@pytest.mark.gui
def test_main_window_renders_initial_offer_list_once(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    render_count = 0
    original_on_search = OfferSearchWidget._on_search

    def counting_on_search(self, *args, **kwargs):
        nonlocal render_count
        render_count += 1
        return original_on_search(self, *args, **kwargs)

    monkeypatch.setattr(OfferSearchWidget, "_on_search", counting_on_search)

    window = MainWindow(load_builtin_data())

    assert render_count == 1
    assert window.offer_search.results_list.count() > 0

    window.close()
    app.quit()
