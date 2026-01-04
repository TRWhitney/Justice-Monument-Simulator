"""Toast notification area for the GUI."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.ui_qt.ui_scale import scale_int


class ToastArea(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._dark = False
        self._ui_scale = 1.0
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(_BASE_TOAST_SPACING)
        self._layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )

    def show_toast(self, message: str, timeout_ms: int = 3000) -> None:
        toast = _Toast(message, dark=self._dark, ui_scale=self._ui_scale)
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

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        self._layout.setSpacing(scale_int(_BASE_TOAST_SPACING, scale))
        for index in range(self._layout.count()):
            item = self._layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, _Toast):
                widget.set_ui_scale(scale)


class _Toast(QtWidgets.QFrame):
    def __init__(
        self,
        message: str,
        dark: bool = False,
        ui_scale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ui_scale = ui_scale
        self._shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(scale_int(_BASE_TOAST_SHADOW_BLUR, ui_scale))
        self._shadow.setOffset(0, scale_int(_BASE_TOAST_SHADOW_OFFSET_Y, ui_scale))
        self.setGraphicsEffect(self._shadow)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._layout = QtWidgets.QHBoxLayout(self)
        self._layout.setContentsMargins(
            scale_int(8, ui_scale),
            scale_int(6, ui_scale),
            scale_int(8, ui_scale),
            scale_int(6, ui_scale),
        )
        label = QtWidgets.QLabel(message)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setWordWrap(True)
        self._layout.addWidget(label)
        self.set_theme(dark)

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        radius = scale_int(_BASE_TOAST_RADIUS, self._ui_scale)
        if dark:
            self.setStyleSheet(
                "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 #2e2e2e, stop:1 #1f1f1f);"
                f"border-radius: {radius}px;"
            )
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 190))
        else:
            self.setStyleSheet(
                "background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 #fff8ee, stop:1 #efe1cc);"
                f"border-radius: {radius}px;"
            )
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 120))

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        self._shadow.setBlurRadius(scale_int(_BASE_TOAST_SHADOW_BLUR, scale))
        self._shadow.setOffset(0, scale_int(_BASE_TOAST_SHADOW_OFFSET_Y, scale))
        self._layout.setContentsMargins(
            scale_int(8, scale),
            scale_int(6, scale),
            scale_int(8, scale),
            scale_int(6, scale),
        )
        self.set_theme(getattr(self, "_dark", False))


_BASE_TOAST_SPACING = 6
_BASE_TOAST_RADIUS = 10
_BASE_TOAST_SHADOW_BLUR = 22
_BASE_TOAST_SHADOW_OFFSET_Y = 5
