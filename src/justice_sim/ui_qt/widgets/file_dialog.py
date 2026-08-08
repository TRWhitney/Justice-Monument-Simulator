"""File dialog with an application-controlled, theme-aware window frame."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from justice_sim.ui_qt.ui_scale import scale_int
from justice_sim.ui_qt.widgets.title_bar import TitleBar


class ThemedFileDialog(QtWidgets.QDialog):
    """Wrap Qt's non-native file browser in the app's frameless window chrome."""

    def __init__(
        self,
        caption: str,
        directory: Path,
        *,
        save: bool,
        dark: bool,
        ui_scale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("themed_file_dialog")
        self.setWindowTitle(f"{caption} — Justice Monument Simulator")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setProperty("dark_theme", dark)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self.windowTitle(), self)
        self.title_bar.set_ui_scale(ui_scale)
        layout.addWidget(self.title_bar)

        self.browser = QtWidgets.QFileDialog(self, caption, str(directory))
        self.browser.setObjectName("file_browser")
        self.browser.setOption(QtWidgets.QFileDialog.Option.DontUseNativeDialog, True)
        self.browser.setWindowFlags(QtCore.Qt.WindowType.Widget)
        if save:
            self.browser.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
            self.browser.setFileMode(QtWidgets.QFileDialog.FileMode.AnyFile)
        else:
            self.browser.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptOpen)
            self.browser.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
        self.browser.accepted.connect(self.accept)
        self.browser.rejected.connect(self.reject)
        layout.addWidget(self.browser, 1)

        self.resize(
            scale_int(720, ui_scale, minimum=600),
            scale_int(500, ui_scale, minimum=420),
        )
        self._apply_theme(dark, ui_scale)

    @property
    def selected_path(self) -> Path | None:
        selected = self.browser.selectedFiles()
        return Path(selected[0]) if selected else None

    def changeEvent(self, event: QtCore.QEvent) -> None:
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def _apply_theme(self, dark: bool, ui_scale: float) -> None:
        palette = (
            {
                "bg": "#1f1f1f",
                "fg": "#e6e6e6",
                "border": "#3a3a3a",
                "field_bg": "#262626",
                "btn_bg": "#2c2c2c",
                "btn_hover": "#3a3a3a",
                "btn_pressed": "#4a4a4a",
                "disabled": "#7a7a7a",
                "selected": "#3f5871",
                "title_bg": "#242424",
                "title_hover": "rgba(255, 255, 255, 0.08)",
                "title_pressed": "rgba(255, 255, 255, 0.16)",
                "close_hover": "#a33838",
                "close_pressed": "#7a2c2c",
            }
            if dark
            else {
                "bg": "#f7f4ee",
                "fg": "#1b1b1b",
                "border": "#d8d2c3",
                "field_bg": "#ffffff",
                "btn_bg": "#f4efe6",
                "btn_hover": "#e5dccb",
                "btn_pressed": "#d6c7b0",
                "disabled": "#9a9a9a",
                "selected": "#dce8f4",
                "title_bg": "#f2ede2",
                "title_hover": "rgba(0, 0, 0, 0.06)",
                "title_pressed": "rgba(0, 0, 0, 0.12)",
                "close_hover": "#d86b6b",
                "close_pressed": "#b95a5a",
            }
        )
        border_w = max(1, scale_int(1, ui_scale))
        radius = scale_int(4, ui_scale, minimum=1)
        pad_v = scale_int(3, ui_scale)
        pad_h = scale_int(6, ui_scale)
        self.setStyleSheet(
            (
                "QDialog#themed_file_dialog {{"
                " background-color: {bg}; color: {fg};"
                " border: {border_w}px solid {border};"
                "}}"
                "QWidget#title_bar {{"
                " background-color: {title_bg}; color: {fg};"
                " border-bottom: {border_w}px solid {border};"
                "}}"
                "QLabel#title_label {{ background: transparent; color: {fg}; font-weight: 600; }}"
                'QToolButton[title_button="true"] {{ background: transparent; color: {fg}; border: none; }}'
                'QToolButton[title_button="true"]:hover {{ background-color: {title_hover}; }}'
                'QToolButton[title_button="true"]:pressed {{ background-color: {title_pressed}; }}'
                'QToolButton[title_role="close"]:hover {{ background-color: {close_hover}; color: white; }}'
                'QToolButton[title_role="close"]:pressed {{ background-color: {close_pressed}; color: white; }}'
                "QFileDialog#file_browser, QFileDialog#file_browser QWidget {{"
                " background-color: {bg}; color: {fg};"
                "}}"
                "QLineEdit, QComboBox, QTreeView, QListView {{"
                " background-color: {field_bg}; color: {fg};"
                " border: {border_w}px solid {border}; border-radius: {radius}px;"
                " padding: {pad_v}px {pad_h}px;"
                "}}"
                "QTreeView::item:selected, QListView::item:selected {{ background-color: {selected}; }}"
                "QHeaderView::section {{"
                " background-color: {btn_bg}; color: {fg};"
                " border: none; border-right: {border_w}px solid {border};"
                " padding: {pad_v}px {pad_h}px;"
                "}}"
                "QPushButton, QToolButton {{"
                " background-color: {btn_bg}; color: {fg};"
                " border: {border_w}px solid {border}; border-radius: {radius}px;"
                " padding: {pad_v}px {pad_h}px;"
                "}}"
                "QPushButton:hover, QToolButton:hover {{ background-color: {btn_hover}; }}"
                "QPushButton:pressed, QToolButton:pressed {{ background-color: {btn_pressed}; }}"
                "QPushButton:disabled, QToolButton:disabled {{ color: {disabled}; }}"
                "QScrollBar {{ background-color: {bg}; }}"
                "QScrollBar::handle {{ background-color: {border}; border-radius: {radius}px; }}"
            ).format(
                **palette,
                border_w=border_w,
                radius=radius,
                pad_v=pad_v,
                pad_h=pad_h,
            )
        )
