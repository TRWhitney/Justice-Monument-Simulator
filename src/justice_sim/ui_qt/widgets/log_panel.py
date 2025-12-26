"""Log panel widget."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.models.offer import JusticeData
from justice_sim.persistence.logs import SessionLog
from justice_sim.ui_qt.widgets.offer_card import OfferCard
from justice_sim.ui_qt.widgets.resource_delta import format_resource_delta_html
from justice_sim.util.render import summarize_offer
from justice_sim.util.search import OfferSearchResult


class LogPanel(QtWidgets.QWidget):
    undo_requested = QtCore.Signal()

    def __init__(
        self, data: JusticeData, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._popover = _LogPopover(data)
        self.destroyed.connect(self._popover.deleteLater)
        self._hover_item: QtWidgets.QListWidgetItem | None = None
        layout = QtWidgets.QVBoxLayout(self)
        self.log_list = QtWidgets.QListWidget()
        self.log_list.setMouseTracking(True)
        self.log_list.viewport().setMouseTracking(True)
        self.log_list.viewport().installEventFilter(self)
        self.log_list.itemEntered.connect(self._on_item_entered)
        self.undo_button = QtWidgets.QPushButton("Undo")
        layout.addWidget(self.log_list)
        layout.addWidget(self.undo_button)
        self.undo_button.clicked.connect(self.undo_requested.emit)

    def update_log(self, log: SessionLog) -> None:
        self._popover.hide()
        self._hover_item = None
        self.log_list.clear()
        for entry in log.entries:
            item = QtWidgets.QListWidgetItem()
            widget = _LogEntryWidget(entry)
            item.setSizeHint(widget.sizeHint())
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entry)
            self.log_list.addItem(item)
            self.log_list.setItemWidget(item, widget)

    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if source is self.log_list.viewport():
            if event.type() == QtCore.QEvent.Type.Leave:
                self._hide_popover()
            elif event.type() == QtCore.QEvent.Type.MouseMove:
                if isinstance(event, QtGui.QMouseEvent):
                    self._handle_viewport_mouse_move(event)
        return super().eventFilter(source, event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._hide_popover()
        super().hideEvent(event)

    def _on_item_entered(self, item: QtWidgets.QListWidgetItem) -> None:
        self._show_popover_for_item(item, QtGui.QCursor.pos())

    def _show_popover_for_item(
        self, item: QtWidgets.QListWidgetItem, cursor_pos: QtCore.QPoint
    ) -> None:
        entry = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if entry is None:
            return
        offer = self._data.offers_by_id.get(entry.offer_id)
        if not offer:
            return
        approve_summary, reject_summary, dismiss_summary = summarize_offer(
            offer, entry.pre_state, self._data
        )
        if entry.action == "dismiss" and dismiss_summary is None:
            dismiss_summary = reject_summary
        result = OfferSearchResult(
            offer=offer,
            npc_name=self._npc_name(offer.npc_id),
            approve_summary=approve_summary,
            reject_summary=reject_summary,
            dismiss_summary=dismiss_summary,
        )
        self._hover_item = item
        self._ensure_popover_parent()
        self._popover.update_card(result, entry.pre_state, entry.action)
        self._popover.move(self._popover_position(cursor_pos))
        self._popover.show()
        self._popover.raise_()

    def _hide_popover(self) -> None:
        self._popover.hide()
        self._hover_item = None
        self._hover_item = None

    def _handle_viewport_mouse_move(self, event: QtGui.QMouseEvent) -> None:
        item = self.log_list.itemAt(event.pos())
        cursor_pos = event.globalPosition().toPoint()
        if item is None:
            self._hide_popover()
            return
        if item is not self._hover_item:
            self._show_popover_for_item(item, cursor_pos)
            return
        if self._popover.isVisible():
            self._popover.move(self._popover_position(cursor_pos))

    def _popover_position(self, cursor_pos: QtCore.QPoint) -> QtCore.QPoint:
        self._popover.adjustSize()
        size = self._popover.sizeHint()
        height = size.height()
        pos = QtCore.QPoint(cursor_pos.x(), cursor_pos.y() - height)
        window = self.window()
        if window is None:
            return pos
        bounds = window.geometry()
        if pos.y() < bounds.top():
            pos.setY(cursor_pos.y() + 12)
        if pos.x() + size.width() > bounds.right():
            pos.setX(bounds.right() - size.width() + 1)
        if pos.x() < bounds.left():
            pos.setX(bounds.left())
        if pos.y() + size.height() > bounds.bottom():
            pos.setY(bounds.bottom() - size.height() + 1)
        if pos.y() < bounds.top():
            pos.setY(bounds.top())
        return window.mapFromGlobal(pos)

    def _npc_name(self, npc_id: str) -> str:
        npc = self._data.npcs_by_id.get(npc_id)
        return npc.name if npc else npc_id

    def _ensure_popover_parent(self) -> None:
        window = self.window()
        if window is None:
            return
        if self._popover.parentWidget() is not window:
            self._popover.setParent(window)


class _LogEntryWidget(QtWidgets.QWidget):
    def __init__(self, entry, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        label = QtWidgets.QLabel(
            format_resource_delta_html(entry.pre_state, entry.post_state)
        )
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setMouseTracking(True)


class _LogPopover(QtWidgets.QFrame):
    def __init__(
        self, data: JusticeData, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.apply_window_attributes()
        self._data = data
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "background-color: #f4f1e8; border: 1px solid #d0c9b3; border-radius: 6px;"
        )

    def apply_window_attributes(self) -> None:
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def update_card(
        self,
        result: OfferSearchResult,
        state,
        action: str,
    ) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        card = OfferCard(
            self._data,
            result,
            state,
            action_filter=action,
        )
        card.setFixedWidth(_LOG_POPOVER_WIDTH)
        card.layout().activate()
        card.adjustSize()
        self._layout.addWidget(card)
        self.adjustSize()


_LOG_POPOVER_WIDTH = 520
