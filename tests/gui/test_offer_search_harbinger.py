import os

import pytest

from justice_sim.models.state import GameState
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget


@pytest.mark.gui
def test_harbinger_forces_search_bar(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    state = GameState(
        case_index=4,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.search_input.setText("hello")
    widget.update_state(state)

    assert widget.search_input.isEnabled()
    assert widget.search_input.text() == "hello"

    forced_state = GameState(
        case_index=5,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    widget.update_state(forced_state)

    assert not widget.search_input.isEnabled()
    assert widget.search_input.text() == "#binger"

    widget.update_state(state)

    assert widget.search_input.isEnabled()
    assert widget.search_input.text() == "hello"

    app.quit()
