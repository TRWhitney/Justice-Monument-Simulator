import os

import pytest

from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget


@pytest.mark.gui
def test_offer_search_preserves_selection_without_spurious_emit(data_dict_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data_dict = data_dict_factory()
    data_dict["offers"] = [
        {
            "id": "offer_scaled",
            "npc_id": "snail",
            "title": "Offer Scaled",
            "text": "Offer scaled text",
            "actions_available": ["approve", "reject"],
            "approve": {
                "effects": [
                    {
                        "type": "add_resource",
                        "params": {
                            "resource": "pop",
                            "amount": {"expr": "2", "scaled_by_case": True},
                        },
                    }
                ]
            },
            "reject": {"effects": []},
        },
        {
            "id": "offer_const_one",
            "npc_id": "snail",
            "title": "Offer Const One",
            "text": "Offer const text",
            "actions_available": ["approve", "reject"],
            "approve": {
                "effects": [
                    {
                        "type": "add_resource",
                        "params": {"resource": "pop", "amount": 2},
                    }
                ]
            },
            "reject": {"effects": []},
        },
        {
            "id": "offer_const_two",
            "npc_id": "snail",
            "title": "Offer Const Two",
            "text": "Offer const text",
            "actions_available": ["approve", "reject"],
            "approve": {
                "effects": [
                    {
                        "type": "add_resource",
                        "params": {"resource": "pop", "amount": 2},
                    }
                ]
            },
            "reject": {"effects": []},
        },
    ]
    data = JusticeData.from_dict(data_dict)
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(400, 300)
    widget.show()
    widget.search_input.setText("$2")
    app.processEvents()

    widget.results_list.setCurrentRow(1)
    app.processEvents()
    selected_id = widget._selected_offer_id()
    assert selected_id is not None

    emitted: list[str] = []
    widget.offer_selected.connect(lambda offer: emitted.append(offer.id))

    next_state = GameState(
        case_index=6,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    widget.update_state(next_state, preserve_scroll=True)
    app.processEvents()

    assert widget._selected_offer_id() == selected_id
    assert emitted == []

    widget.close()
    app.quit()


@pytest.mark.gui
def test_offer_search_clears_selection_when_filter_changes(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(400, 300)
    widget.show()
    widget.update_state(state)
    app.processEvents()

    widget.results_list.setCurrentRow(0)
    app.processEvents()

    emitted: list[object | None] = []
    widget.offer_selected.connect(lambda offer: emitted.append(offer))

    widget.search_input.setText("two")
    app.processEvents()

    assert widget.results_list.currentRow() == -1
    assert emitted == [None]

    widget.close()
    app.quit()
