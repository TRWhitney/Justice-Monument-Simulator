import os
from pathlib import Path

import pytest
from PySide6 import QtCore, QtTest, QtWidgets

from justice_sim.config import load_builtin_data
from justice_sim.ui_qt.app import create_app
from justice_sim.models.offer import EffectSpec, OfferSpec, OutcomeSpec
from justice_sim.models.state import GameState
from justice_sim.ui_qt.widgets.offer_card import (
    OfferCard,
    _ACTION_ICON_WIDTH,
    _EFFECTS_PANEL_PADDING,
    _EFFECTS_PANEL_SPACING,
)
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget
from justice_sim.util.render import summarize_offer
from justice_sim.util.search import OfferSearchResult


@pytest.mark.gui
def test_offer_card_action_spacing():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = load_builtin_data()
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
    npc_name = data.npcs_by_id[offer.npc_id].name

    card = OfferCard(data, result, state)
    card.resize(800, card.sizeHint().height())
    card.show()
    app.processEvents()

    effects_panel = card.findChild(QtWidgets.QWidget, "effects_panel")
    approve_icon = card.findChild(QtWidgets.QLabel, "action_icon_approve")
    approve_effects = card.findChild(QtWidgets.QWidget, "action_effects_approve")
    reject_icon = card.findChild(QtWidgets.QLabel, "action_icon_reject")
    reject_effects = card.findChild(QtWidgets.QWidget, "action_effects_reject")

    assert effects_panel is not None
    assert approve_icon is not None
    assert approve_effects is not None
    assert reject_icon is not None
    assert reject_effects is not None
    assert any(
        label.text() == npc_name for label in card.findChildren(QtWidgets.QLabel)
    )

    assert approve_icon.height() < _ACTION_ICON_WIDTH * 0.6
    assert reject_icon.height() < _ACTION_ICON_WIDTH * 0.6

    panel_top = effects_panel.contentsRect().top()
    top_gap = approve_icon.geometry().top() - panel_top
    assert 1 <= top_gap <= _EFFECTS_PANEL_PADDING + 6

    approve_gap = approve_effects.geometry().top() - approve_icon.geometry().bottom()
    reject_gap = reject_icon.geometry().top() - approve_effects.geometry().bottom()
    reject_effect_gap = (
        reject_effects.geometry().top() - reject_icon.geometry().bottom()
    )
    max_gap = _EFFECTS_PANEL_SPACING + 6
    assert 0 <= approve_gap <= max_gap
    assert 0 <= reject_gap <= max_gap
    assert 0 <= reject_effect_gap <= max_gap

    card.close()
    app.quit()


@pytest.mark.gui
@pytest.mark.parametrize("scale,width", [(1.0, 800), (1.25, 1800)])
def test_grumblo_effects_fit_before_selection_and_after_reuse(scale, width):
    app = create_app()
    data = load_builtin_data()
    widget = OfferSearchWidget(data, GameState(16, 30, 10, 3, 0, 0))
    widget.set_ui_scale(scale)
    widget.resize(width, 800)
    widget.show()

    def settled_card():
        # Let normal Qt layout events run; never repair row sizes from the test.
        QtTest.QTest.qWait(30)
        for index in range(widget.results_list.count()):
            item = widget.results_list.item(index)
            card = widget.results_list.itemWidget(item)
            if "Mystery Gift" in card._title_label.text():
                assert item.sizeHint().height() >= card.heightForWidth(card.width())
                for label in card._effect_labels.values():
                    assert label.height() >= label.heightForWidth(label.width())
                    bottom = label.mapTo(card, label.rect().bottomRight()).y()
                    assert bottom < card.height()
                return index, card
        pytest.fail("Missing Grumblo: Mystery Gift")

    try:
        QtTest.QTest.qWait(30)
        widget.search_input.setText("#grumblo")
        index, card = settled_card()
        assert widget.results_list.currentRow() == -1
        destination = os.environ.get("JUSTICE_LAYOUT_ARTIFACT_DIR")
        if destination:
            directory = Path(destination)
            directory.mkdir(parents=True, exist_ok=True)
            assert card.grab().save(str(directory / f"grumblo-initial-{scale}.png"))
        QtTest.QTest.mouseClick(
            widget.results_list.viewport(),
            QtCore.Qt.MouseButton.LeftButton,
            pos=widget.results_list.visualItemRect(
                widget.results_list.item(index)
            ).center(),
        )
        settled_card()
        widget.search_input.setText("no-such-offer-in-this-dataset")
        QtTest.QTest.qWait(30)
        widget.search_input.setText("#grumblo")
        settled_card()
        widget.resize(width - 150, 700)
        settled_card()
        widget.update_state(GameState(26, 40, 20, 3, 0, 0), preserve_scroll=True)
        settled_card()
        widget.set_ui_scale(scale + 0.25)
        settled_card()
        QtTest.QTest.qWait(30)
        assert not widget._item_size_timer.isActive()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


@pytest.mark.gui
def test_offer_card_height_expands_with_wrap():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = load_builtin_data()
    state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    npc_id = data.npcs[0].id
    long_text = "This is a long effect that should wrap across multiple lines. " * 6
    offer = OfferSpec(
        id="wrap_test_offer",
        npc_id=npc_id,
        title="Wrap Test",
        text="Description",
        actions_available=("approve", "reject"),
        approve=OutcomeSpec(
            effects=(EffectSpec(type="raw_effect", params={"raw": long_text}),)
        ),
        reject=OutcomeSpec(
            effects=(EffectSpec(type="raw_effect", params={"raw": long_text}),)
        ),
        dismiss=None,
        tags=(),
        allow_insufficient_funds=None,
        conditions=(),
        chain=None,
        notes=None,
    )
    approve, reject, dismiss = summarize_offer(offer, state, data)
    result = OfferSearchResult(
        offer=offer,
        npc_name=data.npcs_by_id[npc_id].name,
        approve_summary=approve,
        reject_summary=reject,
        dismiss_summary=dismiss,
    )

    widget = OfferSearchWidget(data, state)
    item = QtWidgets.QListWidgetItem()
    card = OfferCard(data, result, state)
    widget.results_list.addItem(item)
    widget.results_list.setItemWidget(item, card)

    widget.resize(800, 600)
    widget.show()
    app.processEvents()
    widget._update_item_sizes()
    height_wide = item.sizeHint().height()

    widget.resize(360, 600)
    app.processEvents()
    widget._update_item_sizes()
    height_narrow = item.sizeHint().height()

    assert height_narrow > height_wide

    widget.close()
    app.quit()
