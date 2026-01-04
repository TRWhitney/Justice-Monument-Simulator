"""Guided tour panel widget."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.ui_qt.ui_scale import scale_int

_BASE_PANEL_WIDTH = 360
_BASE_MARGIN = 14
_BASE_SPACING = 8
_BASE_RADIUS = 12
_BASE_SHADOW_BLUR = 24
_BASE_SHADOW_OFFSET_Y = 6
_BASE_DIALOG_WIDTH = 420
_BASE_DIALOG_MARGIN = 16
_BASE_DIALOG_RADIUS = 12
_BASE_DIALOG_SHADOW_BLUR = 26
_BASE_DIALOG_SHADOW_OFFSET_Y = 6


class TourPanel(QtWidgets.QFrame):
    next_requested = QtCore.Signal()
    back_requested = QtCore.Signal()
    close_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_scale = 1.0
        self._dark = False
        self._skip_emitted = False
        self.setObjectName("guided_tour_panel")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

        self._shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(_BASE_SHADOW_BLUR)
        self._shadow.setOffset(0, _BASE_SHADOW_OFFSET_Y)
        self.setGraphicsEffect(self._shadow)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(
            _BASE_MARGIN, _BASE_MARGIN, _BASE_MARGIN, _BASE_MARGIN
        )
        self._layout.setSpacing(_BASE_SPACING)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(_BASE_SPACING)
        self.title_label = QtWidgets.QLabel("Welcome")
        self.title_label.setObjectName("tour_title")
        self.title_label.setWordWrap(True)
        self.step_label = QtWidgets.QLabel("")
        self.step_label.setObjectName("tour_step")
        self.step_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop
        )
        header.addWidget(self.title_label, 1)
        header.addWidget(self.step_label, 0)

        self.body_label = QtWidgets.QLabel("")
        self.body_label.setWordWrap(True)
        self.body_label.setObjectName("tour_body")

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(_BASE_SPACING)
        self.back_button = QtWidgets.QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested.emit)
        self.next_button = QtWidgets.QPushButton("Next")
        self.next_button.clicked.connect(self.next_requested.emit)
        self.close_button = QtWidgets.QPushButton("Skip Tour")
        self.close_button.clicked.connect(self.close_requested.emit)
        button_row.addWidget(self.back_button)
        button_row.addWidget(self.next_button)
        button_row.addStretch(1)
        button_row.addWidget(self.close_button)

        self._layout.addLayout(header)
        self._layout.addWidget(self.body_label)
        self._layout.addLayout(button_row)

        self.set_ui_scale(1.0)
        self.set_theme(False)

    def set_step(self, index: int, total: int, title: str, body: str) -> None:
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.step_label.setText(f"{index + 1} / {total}")
        self.back_button.setEnabled(index > 0)
        self.next_button.setText("Finish" if index >= total - 1 else "Next")

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        radius = scale_int(_BASE_RADIUS, self._ui_scale, minimum=1)
        if dark:
            palette = {
                "panel_top": "#2e2e2e",
                "panel_bottom": "#1f1f1f",
                "fg": "#e6e6e6",
                "muted": "#b6b6b6",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 200))
        else:
            palette = {
                "panel_top": "#fff8ee",
                "panel_bottom": "#efe1cc",
                "fg": "#1b1b1b",
                "muted": "#6a5f51",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 130))
        self.setStyleSheet(
            (
                "QFrame#guided_tour_panel {{"
                " background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 {panel_top}, stop:1 {panel_bottom});"
                " border-radius: {radius}px;"
                " color: {fg};"
                "}}"
                "QFrame#guided_tour_panel QLabel {{ background: transparent; }}"
                "QLabel#tour_title {{ font-weight: 700; }}"
                "QLabel#tour_step {{ color: {muted}; }}"
            ).format(**palette, radius=radius)
        )

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        margin = scale_int(_BASE_MARGIN, scale)
        spacing = scale_int(_BASE_SPACING, scale)
        self._layout.setContentsMargins(margin, margin, margin, margin)
        self._layout.setSpacing(spacing)
        self.setFixedWidth(scale_int(_BASE_PANEL_WIDTH, scale, minimum=1))
        self._shadow.setBlurRadius(scale_int(_BASE_SHADOW_BLUR, scale))
        self._shadow.setOffset(0, scale_int(_BASE_SHADOW_OFFSET_Y, scale))
        self.set_theme(self._dark)


class TourStartDialog(QtWidgets.QDialog):
    start_requested = QtCore.Signal()
    skip_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_scale = 1.0
        self._dark = False
        self.setObjectName("guided_tour_prompt")
        self.setWindowTitle("Welcome")
        self.setModal(False)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(
            _BASE_DIALOG_MARGIN,
            _BASE_DIALOG_MARGIN,
            _BASE_DIALOG_MARGIN,
            _BASE_DIALOG_MARGIN,
        )
        root_layout.setSpacing(0)

        self._panel = QtWidgets.QFrame()
        self._panel.setObjectName("tour_prompt_panel")
        self._panel_layout = QtWidgets.QVBoxLayout(self._panel)
        self._panel_layout.setContentsMargins(
            _BASE_DIALOG_MARGIN,
            _BASE_DIALOG_MARGIN,
            _BASE_DIALOG_MARGIN,
            _BASE_DIALOG_MARGIN,
        )
        self._panel_layout.setSpacing(_BASE_SPACING)
        root_layout.addWidget(self._panel)

        self._shadow = QtWidgets.QGraphicsDropShadowEffect(self._panel)
        self._shadow.setBlurRadius(_BASE_DIALOG_SHADOW_BLUR)
        self._shadow.setOffset(0, _BASE_DIALOG_SHADOW_OFFSET_Y)
        self._panel.setGraphicsEffect(self._shadow)

        title = QtWidgets.QLabel("Welcome to Justice Monument Simulator")
        title.setObjectName("tour_prompt_title")
        title.setWordWrap(True)

        body = QtWidgets.QLabel(
            "Would you like to start the guided tour? You can skip it for now."
        )
        body.setWordWrap(True)
        body.setObjectName("tour_prompt_body")

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(_BASE_SPACING)
        self.start_button = QtWidgets.QPushButton("Start Tour")
        self.start_button.setObjectName("tour_start_button")
        self.start_button.clicked.connect(self._on_start)
        self.skip_button = QtWidgets.QPushButton("Skip Tour")
        self.skip_button.setObjectName("tour_skip_button")
        self.skip_button.clicked.connect(self._on_skip)
        button_row.addStretch(1)
        button_row.addWidget(self.skip_button)
        button_row.addWidget(self.start_button)

        self._panel_layout.addWidget(title)
        self._panel_layout.addWidget(body)
        self._panel_layout.addLayout(button_row)

        self.set_ui_scale(1.0)
        self.set_theme(False)

    def _on_start(self) -> None:
        self.start_requested.emit()
        self.accept()

    def _on_skip(self) -> None:
        self._skip_emitted = True
        self.skip_requested.emit()
        super().reject()

    def reject(self) -> None:
        if self.isVisible() and not self._skip_emitted:
            self.skip_requested.emit()
        super().reject()

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        radius = scale_int(_BASE_DIALOG_RADIUS, self._ui_scale, minimum=1)
        if dark:
            palette = {
                "panel_top": "#2e2e2e",
                "panel_bottom": "#1f1f1f",
                "border": "#3a3a3a",
                "btn_bg": "#2c2c2c",
                "btn_hover": "#3a3a3a",
                "btn_pressed": "#4a4a4a",
                "fg": "#e6e6e6",
                "muted": "#b6b6b6",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 200))
        else:
            palette = {
                "panel_top": "#fff8ee",
                "panel_bottom": "#efe1cc",
                "border": "#d8d2c3",
                "btn_bg": "#f4efe6",
                "btn_hover": "#e5dccb",
                "btn_pressed": "#d6c7b0",
                "fg": "#1b1b1b",
                "muted": "#6a5f51",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 130))
        self._panel.setStyleSheet(
            (
                "QFrame#tour_prompt_panel {{"
                " background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 {panel_top}, stop:1 {panel_bottom});"
                " border-radius: {radius}px;"
                " color: {fg};"
                "}}"
                "QFrame#tour_prompt_panel QLabel {{ background: transparent; }}"
                "QLabel#tour_prompt_title {{ font-weight: 700; }}"
                "QLabel#tour_prompt_body {{ color: {fg}; }}"
                "QPushButton {{ background-color: {btn_bg};"
                " border: 1px solid {border};"
                " border-radius: {radius}px;"
                " padding: 4px 10px; }}"
                "QPushButton:hover {{ background-color: {btn_hover}; }}"
                "QPushButton:pressed {{ background-color: {btn_pressed}; }}"
            ).format(**palette, radius=radius)
        )

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        margin = scale_int(_BASE_DIALOG_MARGIN, scale)
        spacing = scale_int(_BASE_SPACING, scale)
        self._panel_layout.setContentsMargins(margin, margin, margin, margin)
        self._panel_layout.setSpacing(spacing)
        self.setFixedWidth(scale_int(_BASE_DIALOG_WIDTH, scale, minimum=1))
        self._shadow.setBlurRadius(scale_int(_BASE_DIALOG_SHADOW_BLUR, scale))
        self._shadow.setOffset(0, scale_int(_BASE_DIALOG_SHADOW_OFFSET_Y, scale))
        self.set_theme(self._dark)
