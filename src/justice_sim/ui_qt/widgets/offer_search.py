"""Offer search widget."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.engine.encounter import (
    UniformEncounterModel,
    eligible_harbinger_offers,
)
from justice_sim.engine.effects import resolve_probability
from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.ui_qt.widgets.offer_card import OfferCard
from justice_sim.util.assets import resolve_npc_image_path
from justice_sim.util.search import (
    OfferSearchResult,
    normalize_npc_query,
    npc_matches_query,
    parse_search_query,
    search_offers,
)


class _NpcButtonBar(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: list[QtWidgets.QToolButton] = []
        self._hspacing = 6
        self._vspacing = 6

    def add_button(self, button: QtWidgets.QToolButton) -> None:
        button.setParent(self)
        self._buttons.append(button)
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(width, test_only=True)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, self._do_layout(self.width(), test_only=True))

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, self._do_layout(self.width(), test_only=True))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._do_layout(event.size().width(), test_only=False)

    def _do_layout(self, width: int, test_only: bool) -> int:
        margins = self.contentsMargins()
        left = margins.left()
        top = margins.top()
        right = margins.right()
        bottom = margins.bottom()
        available_width = max(0, width - left - right)
        y = top
        row: list[QtWidgets.QToolButton] = []
        row_width = 0
        row_height = 0

        def flush_row() -> None:
            nonlocal y, row, row_width, row_height
            if not row:
                return
            row_x = left + max(0, (available_width - row_width) // 2)
            for index, button in enumerate(row):
                if index > 0:
                    row_x += self._hspacing
                if not test_only:
                    button.setGeometry(
                        QtCore.QRect(row_x, y, button.sizeHint().width(), row_height)
                    )
                row_x += button.sizeHint().width()
            y += row_height + self._vspacing
            row = []
            row_width = 0
            row_height = 0

        for button in self._buttons:
            size = button.sizeHint()
            next_width = (
                size.width() if not row else row_width + self._hspacing + size.width()
            )
            if row and next_width > available_width:
                flush_row()
            if row:
                row_width += self._hspacing + size.width()
            else:
                row_width = size.width()
            row_height = max(row_height, size.height())
            row.append(button)

        flush_row()
        if y > top:
            y -= self._vspacing
        return y + bottom


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
        self._forced_query: str | None = None
        self._encounter_model = UniformEncounterModel()
        self._npc_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._npc_button_effects: dict[str, QtWidgets.QGraphicsOpacityEffect] = {}
        self._npc_queries: dict[str, str] = {}
        self._auto_offer_id: str | None = None
        self._show_all_restore_state = False

        layout = QtWidgets.QVBoxLayout(self)
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText(
            "Search offers (#npc or #npc_name_with_underscores, $term for effects)"
        )
        self.show_all_toggle = QtWidgets.QToolButton(self.search_input)
        self.show_all_toggle.setCheckable(True)
        self.show_all_toggle.setChecked(False)
        self.show_all_toggle.setText("Show All")
        self.show_all_toggle.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.show_all_toggle.setToolTip("Ignore offer conditions and show every offer.")
        self.show_all_toggle.setStyleSheet(
            "QToolButton { border: none; padding: 2px 6px; border-radius: 8px; }"
            "QToolButton:checked { background-color: rgba(0, 0, 0, 0.12);"
            " font-weight: 600; }"
        )
        self._npc_filter_bar = self._build_npc_filter_bar()
        self.results_list = QtWidgets.QListWidget()
        self.results_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.results_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        layout.addWidget(self.search_input)
        layout.addWidget(self._npc_filter_bar)
        layout.addWidget(self.results_list)

        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.show_all_toggle.toggled.connect(self._on_show_all_toggled)
        self.results_list.itemSelectionChanged.connect(self._on_selection)
        self.search_input.installEventFilter(self)
        self._position_show_all_toggle()

    def _on_search_text_changed(self, text: str) -> None:
        self._on_search(text)

    def _on_show_all_toggled(self, _checked: bool) -> None:
        self._apply_forced_filter()
        self._on_search(self.search_input.text())

    def set_auto_offer_id(self, offer_id: str | None) -> None:
        self._auto_offer_id = offer_id

    def set_show_all_visible(self, visible: bool) -> None:
        if not visible:
            self._show_all_restore_state = self.show_all_toggle.isChecked()
            if self._show_all_restore_state:
                self.show_all_toggle.setChecked(False)
        elif self._show_all_restore_state:
            self.show_all_toggle.setChecked(True)
        self.show_all_toggle.setVisible(visible)
        self._position_show_all_toggle()

    def can_accept_typed_input(self) -> bool:
        return (
            self.search_input.isEnabled()
            and self.search_input.isVisible()
            and not self.search_input.isReadOnly()
        )

    def focus_search_input(self, text: str | None = None) -> bool:
        if not self.can_accept_typed_input():
            return False
        self.search_input.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        if text:
            self.search_input.insert(text)
        return True

    def _on_search(
        self,
        text: str,
        *,
        preserve_scroll: bool = False,
        selected_offer_id: str | None = None,
    ) -> None:
        previous_selected_id = self._selected_offer_id()
        if not self._forced_filter:
            self._previous_text = text
        scroll_value = (
            self.results_list.verticalScrollBar().value() if preserve_scroll else None
        )
        blocker = QtCore.QSignalBlocker(self.results_list)
        npc_query, terms, effect_terms = parse_search_query(text)
        eligible_ids = self._eligible_offer_ids()
        if self.show_all_toggle.isChecked() and not self._is_offer_locked():
            eligible_ids = None
        self._results = search_offers(
            text, self._data, self._state, eligible_offer_ids=eligible_ids
        )
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
                npc_highlight=npc_query.replace("_", " ") if npc_query else None,
            )
            item.setSizeHint(card.sizeHint())
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, card)
        self._update_item_sizes()
        restored = False
        pending_emit = False
        if self._auto_offer_id:
            restored = self._restore_selection(self._auto_offer_id)
            pending_emit = restored and previous_selected_id != self._auto_offer_id
            if not restored:
                self._clear_selection()
        else:
            if selected_offer_id:
                restored = self._restore_selection(selected_offer_id)
            if not restored and previous_selected_id:
                self._clear_selection()
        del blocker
        if scroll_value is not None:
            self.results_list.verticalScrollBar().setValue(scroll_value)
        if pending_emit:
            self._on_selection()
        self._update_npc_filter_buttons(text)
        self._update_selection_styles()

    def _on_selection(self) -> None:
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self._results):
            return
        self.offer_selected.emit(self._results[row].offer)
        self._update_selection_styles()

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

    def clear_selection(self) -> None:
        self._clear_selection()

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
        if self._auto_offer_id:
            forced_query = self._forced_filter_query()
            if forced_query and not self._forced_filter:
                self._previous_text = self.search_input.text()
                self._forced_filter = True
                self._forced_query = forced_query
                self._set_search_text(forced_query)
                self.search_input.setReadOnly(True)
                self._npc_filter_bar.setEnabled(False)
                return True
            if not forced_query and self._forced_filter:
                self._forced_filter = False
                self._forced_query = None
                self.search_input.setReadOnly(False)
                self._set_search_text(self._previous_text)
                self._npc_filter_bar.setEnabled(True)
                return True
            if forced_query:
                changed = forced_query != self._forced_query
                self._forced_query = forced_query
                self._set_search_text(forced_query)
                self.search_input.setReadOnly(True)
                self._npc_filter_bar.setEnabled(False)
                return changed
            return False
        forced_query = self._forced_filter_query()
        if forced_query and not self._forced_filter:
            self._previous_text = self.search_input.text()
            self._forced_filter = True
            self._forced_query = forced_query
            self._set_search_text(forced_query)
            self.search_input.setReadOnly(True)
            self._npc_filter_bar.setEnabled(False)
            return True
        if not forced_query and self._forced_filter:
            self._forced_filter = False
            self._forced_query = None
            self.search_input.setReadOnly(False)
            self._set_search_text(self._previous_text)
            self._npc_filter_bar.setEnabled(True)
            return True
        if forced_query:
            changed = forced_query != self._forced_query
            self._forced_query = forced_query
            self._set_search_text(forced_query)
            self.search_input.setReadOnly(True)
            self._npc_filter_bar.setEnabled(False)
            return changed
        return False

    def _eligible_offer_ids(self) -> set[str] | None:
        if self._auto_offer_id:
            return {self._auto_offer_id}
        forced_offer = self._forced_offer_id()
        if forced_offer:
            return {forced_offer}
        override_ids = self._forced_override_offer_ids()
        if override_ids:
            return set(override_ids)
        if self._should_force_harbinger():
            eligible = set(eligible_harbinger_offers(self._state, self._data))
            grateful_rule = self._data.special_rules.gratefulbinger
            if grateful_rule:
                eligible.add(grateful_rule.offer_id)
            return eligible
        return set(self._encounter_model.eligible_offers(self._state, self._data))

    def _set_search_text(self, text: str) -> None:
        blocker = QtCore.QSignalBlocker(self.search_input)
        self.search_input.setText(text)
        del blocker

    def _selected_offer_id(self) -> str | None:
        row = self.results_list.currentRow()
        if 0 <= row < len(self._results):
            return self._results[row].offer.id
        return None

    def _restore_selection(self, offer_id: str) -> bool:
        index = next(
            (
                idx
                for idx, result in enumerate(self._results)
                if result.offer.id == offer_id
            ),
            None,
        )
        if index is None:
            return False
        blocker = QtCore.QSignalBlocker(self.results_list)
        self.results_list.setCurrentRow(index)
        del blocker
        self._update_selection_styles()
        return True

    def _clear_selection(self) -> None:
        blocker = QtCore.QSignalBlocker(self.results_list)
        self.results_list.setCurrentRow(-1)
        del blocker
        self.offer_selected.emit(None)

    def _should_force_harbinger(self) -> bool:
        if self._state.ended:
            return False
        modulus = self._data.special_rules.harbinger.cadence_modulus
        if modulus <= 0:
            return False
        return self._state.case_index % modulus == 0

    def _forced_filter_query(self) -> str | None:
        if self._auto_offer_id:
            return self._query_for_offer_id(self._auto_offer_id)
        forced_offer = self._forced_offer_id()
        if forced_offer:
            return self._query_for_offer_id(forced_offer)
        override_ids = self._forced_override_offer_ids()
        if override_ids:
            return self._query_for_offer_id(override_ids[0])
        if self._should_force_harbinger():
            return "#binger"
        return None

    def _forced_override_info(self) -> tuple[list[str], str | None]:
        if self._state.ended:
            return ([], None)
        harbinger_case = self._should_force_harbinger()
        eligible_ids = set(
            self._encounter_model.eligible_offers(self._state, self._data)
        )
        ordered = sorted(
            enumerate(self._state.encounter_overrides),
            key=lambda item: (-item[1].priority, item[0]),
        )
        for _, override in ordered:
            if harbinger_case and not override.allow_harbinger:
                continue
            if override.probability is not None:
                try:
                    probability = resolve_probability(
                        override.probability, self._state, self._data
                    )
                except Exception:
                    continue
                if probability < 1:
                    return ([], None)
            if override.offer_id and override.offer_id in eligible_ids:
                return ([override.offer_id], "offer")
            if override.npc_id:
                offers = [
                    offer.id
                    for offer in self._data.offers
                    if offer.npc_id == override.npc_id and offer.id in eligible_ids
                ]
                if offers:
                    return (offers, "npc")
        return ([], None)

    def _forced_offer_id(self) -> str | None:
        for forced in self._state.forced_encounters:
            if forced.trigger_case_index == self._state.case_index:
                return forced.offer_id
        return None

    def _forced_override_offer_ids(self) -> list[str]:
        return self._forced_override_info()[0]

    def _forced_override_scope(self) -> str | None:
        return self._forced_override_info()[1]

    def _is_offer_locked(self) -> bool:
        if self._auto_offer_id or self._forced_offer_id():
            return True
        return self._forced_override_scope() == "offer"

    def _query_for_offer_id(self, offer_id: str) -> str:
        offer = self._data.offers_by_id.get(offer_id)
        if not offer:
            return ""
        return f"#{offer.npc_id}"

    def _build_npc_filter_bar(self) -> QtWidgets.QWidget:
        container = _NpcButtonBar()
        container.setContentsMargins(4, 2, 4, 2)

        for npc in self._npc_filter_npcs():
            button = QtWidgets.QToolButton()
            button.setAutoRaise(True)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setIconSize(QtCore.QSize(28, 28))
            button.setToolTip(npc.name)
            button.setAccessibleName(npc.name)
            icon = self._load_npc_icon(npc)
            if icon is not None:
                button.setIcon(icon)
            else:
                button.setText(npc.name[:1].upper())
            button.clicked.connect(
                lambda checked=False, npc_id=npc.id: self._on_npc_button_clicked(npc_id)
            )
            effect = QtWidgets.QGraphicsOpacityEffect(button)
            effect.setOpacity(1.0)
            button.setGraphicsEffect(effect)
            container.add_button(button)
            self._npc_buttons[npc.id] = button
            self._npc_button_effects[npc.id] = effect
            self._npc_queries[npc.id] = normalize_npc_query(npc.name)

        container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        return container

    def _npc_filter_npcs(self) -> list:
        npc_ids = {offer.npc_id for offer in self._data.offers}
        npcs = [
            self._data.npcs_by_id[npc_id]
            for npc_id in npc_ids
            if npc_id in self._data.npcs_by_id
        ]
        return sorted(npcs, key=lambda npc: npc.name.lower())

    def _load_npc_icon(self, npc) -> QtGui.QIcon | None:
        path = resolve_npc_image_path(self._data, npc)
        if path is None or not path.exists():
            return None
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            return None
        return QtGui.QIcon(pixmap)

    def _on_npc_button_clicked(self, npc_id: str) -> None:
        if self._forced_filter:
            return
        npc_query = self._npc_queries.get(npc_id, "")
        if not npc_query:
            return
        self._set_search_text(f"#{npc_query}")
        self._on_search(self.search_input.text())

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self.search_input and event.type() in {
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        }:
            self._position_show_all_toggle()
        return super().eventFilter(obj, event)

    def _position_show_all_toggle(self) -> None:
        if not self.show_all_toggle.isVisible():
            self.search_input.setTextMargins(0, 0, 0, 0)
            return
        rect = self.search_input.rect()
        padding = 4
        height = max(18, rect.height() - padding * 2)
        self.show_all_toggle.setFixedHeight(height)
        self.show_all_toggle.adjustSize()
        width = self.show_all_toggle.sizeHint().width() + 4
        self.show_all_toggle.setFixedWidth(width)
        x = rect.right() - width - padding
        y = (rect.height() - height) // 2
        self.show_all_toggle.move(x, y)
        self.search_input.setTextMargins(0, 0, width + padding * 2, 0)

    def _update_npc_filter_buttons(self, text: str) -> None:
        npc_query, _, _ = parse_search_query(text)
        if not self._npc_buttons:
            return
        if not npc_query:
            for effect in self._npc_button_effects.values():
                effect.setOpacity(1.0)
            return
        for npc_id, button in self._npc_buttons.items():
            npc = self._data.npcs_by_id.get(npc_id)
            npc_name = npc.name if npc else npc_id
            matches = npc_matches_query(npc_name, npc_id, npc_query)
            effect = self._npc_button_effects.get(npc_id)
            if effect is not None:
                effect.setOpacity(1.0 if matches else 0.25)

    def _update_selection_styles(self) -> None:
        selected_item = self.results_list.currentItem()
        for index in range(self.results_list.count()):
            item = self.results_list.item(index)
            card = self.results_list.itemWidget(item)
            if card is None:
                continue
            card.setProperty("selected", item is selected_item)
            card.style().unpolish(card)
            card.style().polish(card)
            card.update()
