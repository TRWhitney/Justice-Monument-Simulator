"""Offer search widget."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.ui_qt.widgets.offer_card import OfferCard
from justice_sim.util.search import (
    OfferSearchResult,
    parse_search_query,
    search_offers,
)


class OfferSearchWidget(QtWidgets.QWidget):
    offer_selected = QtCore.Signal(object)

    def __init__(
        self,
        data: JusticeData,
        state: GameState,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._state = state
        self._results: list[OfferSearchResult] = []
        self._forced_filter = False
        self._previous_text = ""

        layout = QtWidgets.QVBoxLayout(self)
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText(
            "Search offers (#npc for NPC filter, $term for effects)"
        )
        self.results_list = QtWidgets.QListWidget()
        self.results_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.results_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self.search_input)
        layout.addWidget(self.results_list)

        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.results_list.itemSelectionChanged.connect(self._on_selection)

    def _on_search_text_changed(self, text: str) -> None:
        self._on_search(text)

    def _on_search(
        self,
        text: str,
        *,
        preserve_scroll: bool = False,
        selected_offer_id: str | None = None,
    ) -> None:
        if not self._forced_filter:
            self._previous_text = text
        scroll_value = (
            self.results_list.verticalScrollBar().value() if preserve_scroll else None
        )
        blocker = (
            QtCore.QSignalBlocker(self.results_list) if selected_offer_id else None
        )
        self._results = search_offers(text, self._data, self._state)
        npc_query, terms, effect_terms = parse_search_query(text)
        highlight_terms = terms
        self.results_list.clear()
        for result in self._results:
            item = QtWidgets.QListWidgetItem()
            card = OfferCard(
                self._data,
                result,
                self._state,
                highlight_terms=highlight_terms,
                effect_highlight_terms=effect_terms,
                npc_highlight=npc_query,
            )
            item.setSizeHint(card.sizeHint())
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, card)
        self._update_item_sizes()
        if selected_offer_id:
            self._restore_selection(selected_offer_id)
        if blocker is not None:
            del blocker
        if scroll_value is not None:
            self.results_list.verticalScrollBar().setValue(scroll_value)

    def _on_selection(self) -> None:
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self._results):
            return
        self.offer_selected.emit(self._results[row].offer)

    def update_state(self, state: GameState, preserve_scroll: bool = False) -> None:
        self._state = state
        previous_text = self.search_input.text()
        selected_offer_id = self._selected_offer_id()
        forced_changed = self._apply_forced_filter()
        preserve = (
            preserve_scroll
            and not forced_changed
            and self.search_input.text() == previous_text
        )
        self._on_search(
            self.search_input.text(),
            preserve_scroll=preserve,
            selected_offer_id=selected_offer_id if preserve else None,
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_item_sizes()

    def _update_item_sizes(self) -> None:
        viewport_width = self.results_list.viewport().width()
        for index in range(self.results_list.count()):
            item = self.results_list.item(index)
            card = self.results_list.itemWidget(item)
            if card is None:
                continue
            card.setFixedWidth(viewport_width)
            card.setMinimumHeight(0)
            card.layout().activate()
            height = card.heightForWidth(viewport_width)
            if height <= 0:
                card.adjustSize()
                height = card.sizeHint().height()
            item.setSizeHint(QtCore.QSize(viewport_width, height))

    def _apply_forced_filter(self) -> bool:
        should_force = self._should_force_harbinger()
        if should_force and not self._forced_filter:
            self._previous_text = self.search_input.text()
            self._forced_filter = True
            self._set_search_text("#binger")
            self.search_input.setEnabled(False)
            return True
        elif not should_force and self._forced_filter:
            self._forced_filter = False
            self.search_input.setEnabled(True)
            self._set_search_text(self._previous_text)
            return True
        elif should_force:
            self._set_search_text("#binger")
            self.search_input.setEnabled(False)
        return False

    def _set_search_text(self, text: str) -> None:
        blocker = QtCore.QSignalBlocker(self.search_input)
        self.search_input.setText(text)
        del blocker

    def _selected_offer_id(self) -> str | None:
        row = self.results_list.currentRow()
        if 0 <= row < len(self._results):
            return self._results[row].offer.id
        return None

    def _restore_selection(self, offer_id: str) -> None:
        index = next(
            (
                idx
                for idx, result in enumerate(self._results)
                if result.offer.id == offer_id
            ),
            None,
        )
        if index is None:
            return
        blocker = QtCore.QSignalBlocker(self.results_list)
        self.results_list.setCurrentRow(index)
        del blocker

    def _should_force_harbinger(self) -> bool:
        if self._state.ended:
            return False
        modulus = self._data.special_rules.harbinger.cadence_modulus
        if modulus <= 0:
            return False
        return self._state.case_index % modulus == 0
