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
