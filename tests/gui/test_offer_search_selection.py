import os

import pytest
from PySide6 import QtWidgets

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
                            "amount": {"expr": "2", "scaling": "case"},
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


@pytest.mark.gui
def test_offer_search_shows_ranking_suffix_when_unfiltered(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(500, 320)
    widget.show()
    widget.update_state(state)
    app.processEvents()

    item = widget.results_list.item(0)
    card = widget.results_list.itemWidget(item)
    assert card is not None
    title_label = card.findChild(QtWidgets.QLabel, "offer_title_label")
    assert title_label is not None
    title_text = title_label.text()
    assert '(<span style="color:' in title_text
    assert "</span>)" in title_text

    widget.close()
    app.quit()


@pytest.mark.gui
def test_offer_search_hides_ranking_suffix_when_filtered(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(500, 320)
    widget.show()
    widget.search_input.setText("offer")
    app.processEvents()

    item = widget.results_list.item(0)
    card = widget.results_list.itemWidget(item)
    assert card is not None
    title_label = card.findChild(QtWidgets.QLabel, "offer_title_label")
    assert title_label is not None
    title_text = title_label.text()
    assert "(" not in title_text
    assert ")" not in title_text
    assert '<span style="color:' not in title_text

    widget.close()
    app.quit()


@pytest.mark.gui
def test_offer_search_show_all_uses_all_offer_rank_pool(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(500, 320)
    widget.show()
    widget.show_all_toggle.setChecked(True)
    app.processEvents()

    assert widget.results_list.count() == len(data.offers)
    item = widget.results_list.item(0)
    card = widget.results_list.itemWidget(item)
    assert card is not None
    title_label = card.findChild(QtWidgets.QLabel, "offer_title_label")
    assert title_label is not None
    title_text = title_label.text()
    assert "/5" in title_text
    assert '(<span style="color:' in title_text

    widget.close()
    app.quit()


@pytest.mark.gui
def test_offer_search_clear_filter_button_clears_and_dims(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    state = GameState(
        case_index=1,
        coins=5,
        pop=3,
        mh=1,
        dismissals=0,
        retirement_chests=0,
    )
    widget = OfferSearchWidget(data, state)
    widget.resize(500, 320)
    widget.show()
    widget.update_state(state)
    app.processEvents()

    clear_button = widget._clear_npc_filter_button
    assert clear_button is not None
    assert widget._npc_filter_bar._buttons[-1] is clear_button

    first_npc_button = next(iter(widget._npc_buttons.values()))
    assert clear_button.iconSize() == first_npc_button.iconSize()
    assert clear_button.size() == first_npc_button.size()

    clear_effect = widget._clear_npc_filter_effect
    assert clear_effect is not None
    assert clear_effect.opacity() == 0.25

    first_npc_button.click()
    app.processEvents()

    assert widget.search_input.text().startswith("#")
    assert clear_effect.opacity() == 1.0

    clear_button.click()
    app.processEvents()

    assert widget.search_input.text() == ""
    assert clear_effect.opacity() == 0.25

    widget.close()
    app.quit()
