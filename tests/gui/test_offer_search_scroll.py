import os

import pytest

from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget


@pytest.mark.gui
def test_offer_search_preserves_scroll(data_dict_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data_dict = data_dict_factory()
    base_offer = data_dict["offers"][0]
    for index in range(30):
        data_dict["offers"].append(
            {
                "id": f"offer_extra_{index}",
                "npc_id": base_offer["npc_id"],
                "title": f"Offer Extra {index}",
                "text": "More text",
                "actions_available": ["approve", "reject"],
                "approve": base_offer["approve"],
                "reject": base_offer["reject"],
            }
        )
    data = JusticeData.from_dict(data_dict)
    state = GameState(
        case_index=1,
        coins=0,
        pop=1,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(400, 300)
    widget.show()
    widget.search_input.setText("Offer")
    app.processEvents()

    scrollbar = widget.results_list.verticalScrollBar()
    assert scrollbar.maximum() > 0
    target = scrollbar.maximum() // 2
    scrollbar.setValue(target)
    app.processEvents()

    widget.update_state(state, preserve_scroll=True)
    app.processEvents()

    assert scrollbar.value() == target

    widget.close()
    app.quit()
