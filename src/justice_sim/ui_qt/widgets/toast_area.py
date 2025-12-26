"""Toast notification area for the GUI."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class ToastArea(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

    def show_toast(self, message: str, timeout_ms: int = 3000) -> None:
        toast = _Toast(message)
        self._layout.insertWidget(0, toast)
        QtCore.QTimer.singleShot(timeout_ms, lambda: self._remove_toast(toast))

    def toast_count(self) -> int:
        return self._layout.count()

    def _remove_toast(self, toast: QtWidgets.QWidget) -> None:
        if toast.parent() is None:
            return
        self._layout.removeWidget(toast)
        toast.setParent(None)
        toast.deleteLater()


class _Toast(QtWidgets.QFrame):
    def __init__(self, message: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "background-color: #f4f1e8; border: 1px solid #d0c9b3; border-radius: 6px;"
        )
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        label = QtWidgets.QLabel(message)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)
