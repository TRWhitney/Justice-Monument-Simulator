"""Reusable frameless-window title bar."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.ui_qt.ui_scale import scale_int


class TitleBar(QtWidgets.QWidget):
    """Title bar controls for windows whose frame is drawn by the application."""

    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("title_bar")
        self._drag_pos: QtCore.QPoint | None = None
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(8, 4, 8, 4)
        self._layout.setSpacing(6)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("title_label")
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.title_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        self.min_button = self._make_button("—", "Minimize")
        self.max_button = self._make_button("□", "Maximize")
        self.close_button = self._make_button("✕", "Close", role="close")

        self.min_button.clicked.connect(self._on_minimize)
        self.max_button.clicked.connect(self._on_maximize_restore)
        self.close_button.clicked.connect(self._on_close)

        self._layout.addWidget(self.title_label)
        self._layout.addStretch(1)
        self._layout.addWidget(self.min_button)
        self._layout.addWidget(self.max_button)
        self._layout.addWidget(self.close_button)
        self.set_ui_scale(1.0)

    def _make_button(
        self, text: str, tooltip: str, role: str = "default"
    ) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.setFixedSize(28, 24)
        button.setProperty("title_button", True)
        button.setProperty("title_role", role)
        return button

    def set_ui_scale(self, scale: float) -> None:
        self._layout.setContentsMargins(
            scale_int(8, scale),
            scale_int(4, scale),
            scale_int(8, scale),
            scale_int(4, scale),
        )
        self._layout.setSpacing(scale_int(6, scale))
        width = scale_int(28, scale, minimum=1)
        height = scale_int(24, scale, minimum=1)
        for button in (self.min_button, self.max_button, self.close_button):
            button.setFixedSize(width, height)

    def set_maximized(self, maximized: bool) -> None:
        self.max_button.setText("❐" if maximized else "□")
        self.max_button.setToolTip("Restore" if maximized else "Maximize")

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._on_maximize_restore()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if _is_titlebar_button(child):
                super().mousePressEvent(event)
                return
            if self.window().isMaximized():
                super().mousePressEvent(event)
                return
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint() - self.window().pos()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._drag_pos is not None
            and event.buttons() & QtCore.Qt.MouseButton.LeftButton
        ):
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _on_minimize(self) -> None:
        self.window().showMinimized()

    def _on_maximize_restore(self) -> None:
        if self.window().isMaximized():
            self.window().showNormal()
        else:
            self.window().showMaximized()

    def _on_close(self) -> None:
        self.window().close()


def _is_titlebar_button(widget: QtWidgets.QWidget | None) -> bool:
    current = widget
    while current is not None:
        if isinstance(current, QtWidgets.QAbstractButton):
            return True
        current = current.parentWidget()
    return False
