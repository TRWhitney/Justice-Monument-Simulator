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


def _card_labels(card):
    return [label.text() for label in card.findChildren(QtWidgets.QLabel)]


@pytest.mark.gui
def test_reused_search_cards_match_fresh_content(builtin_data):
    from dataclasses import replace

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    state = GameState(1, 5, 3, 1, 0, 0)
    widget = OfferSearchWidget(builtin_data, state)
    widget.resize(770, 600)
    widget.show()
    app.processEvents()
    original = widget.results_list.itemWidget(widget.results_list.item(0))
    try:
        widget.search_input.setText("c")
        assert widget.results_list.itemWidget(widget.results_list.item(0)) is original
        for query in ("coin", "#grumblo", "$+1", "no_such_offer", ""):
            widget.search_input.setText(query)
            app.processEvents()
            fresh = OfferSearchWidget(builtin_data, state)
            try:
                fresh.resize(770, 600)
                fresh.show()
                fresh.search_input.setText(query)
                app.processEvents()
                assert widget._results == fresh._results
                for row in range(widget.results_list.count()):
                    actual = widget.results_list.itemWidget(
                        widget.results_list.item(row)
                    )
                    expected = fresh.results_list.itemWidget(
                        fresh.results_list.item(row)
                    )
                    assert _card_labels(actual) == _card_labels(expected)
                    assert (
                        actual._npc_image_label.pixmap().toImage()
                        == expected._npc_image_label.pixmap().toImage()
                    )
            finally:
                fresh.close()
                fresh.deleteLater()
        # A changed state must refresh both scaled effects and cached rankings.
        state = replace(state, case_index=6, coins=99)
        widget.update_state(state)
        fresh = OfferSearchWidget(builtin_data, state)
        try:
            assert widget._results == fresh._results
            for row in range(widget.results_list.count()):
                assert _card_labels(
                    widget.results_list.itemWidget(widget.results_list.item(row))
                ) == _card_labels(
                    fresh.results_list.itemWidget(fresh.results_list.item(row))
                )
        finally:
            fresh.close()
            fresh.deleteLater()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
        app.quit()


@pytest.mark.gui
def test_empty_search_recycles_cards_and_scale_discards_old_sizes(data_factory):
    from PySide6 import QtCore

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    widget = OfferSearchWidget(data_factory(), GameState(1, 5, 3, 1, 0, 0))
    try:
        original = [
            widget.results_list.itemWidget(widget.results_list.item(i))
            for i in range(widget.results_list.count())
        ]
        widget.search_input.setText("no_such_offer")
        assert widget.results_list.count() == 0
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )
        widget.search_input.clear()
        assert [
            widget.results_list.itemWidget(widget.results_list.item(i))
            for i in range(widget.results_list.count())
        ] == original
        widget.search_input.setText("no_such_offer")
        widget.set_ui_scale(1.3)
        widget.search_input.clear()
        assert (
            widget.results_list.itemWidget(widget.results_list.item(0))._ui_scale == 1.3
        )
        assert (
            widget.results_list.itemWidget(widget.results_list.item(0))
            is not original[0]
        )
    finally:
        widget.close()
        widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(
            None, QtCore.QEvent.Type.DeferredDelete
        )
        app.quit()
