"""Toast notification area for the GUI."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class ToastArea(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

    def show_toast(self, message: str, timeout_ms: int = 3000) -> None:
        toast = _Toast(message, dark=self._dark)
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

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        for index in range(self._layout.count()):
            item = self._layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, _Toast):
                widget.set_theme(dark)


class _Toast(QtWidgets.QFrame):
    def __init__(
        self, message: str, dark: bool = False, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 5)
        self.setGraphicsEffect(self._shadow)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.set_theme(dark)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        label = QtWidgets.QLabel(message)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

    def set_theme(self, dark: bool) -> None:
        if dark:
            self.setStyleSheet(
                "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 #2e2e2e, stop:1 #1f1f1f);"
                "border-radius: 10px;"
            )
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 190))
        else:
            self.setStyleSheet(
                "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 #fff8ee, stop:1 #efe1cc);"
                "border-radius: 10px;"
            )
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 120))
