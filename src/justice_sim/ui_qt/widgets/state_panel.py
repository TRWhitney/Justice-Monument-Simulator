"""State display widget."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.models.state import GameState

_RESOURCE_ROWS = (
    ("case_index", "Case", None, False, True, None),
    ("coins", "Coins", "court_coin.png", True, False, None),
    ("pop", "Popularity", "pop.png", True, False, None),
    ("mh", "Health", "mental_health.png", True, False, None),
    ("dismissals", "Dismissals", "dismissal.png", True, False, None),
    ("retirement_chests", "Chests", "chest.png", False, False, 28),
)
_ICON_SIZE = 22
_ICON_TEXT_WIDTH = 44
_BUTTON_WIDTH = 36
_VALUE_MIN_WIDTH = 48


class _ResourceRow(QtWidgets.QWidget):
    adjusted = QtCore.Signal(str, int)

    def __init__(
        self,
        resource: str,
        label: str,
        icon_path: Path | None,
        adjustable: bool = True,
        emphasize: bool = False,
        icon_size: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resource = resource
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        self.decrease_button: QtWidgets.QPushButton | None = None
        if adjustable:
            self.decrease_button = QtWidgets.QPushButton("-")
            self.decrease_button.setFixedWidth(_BUTTON_WIDTH)
            self.decrease_button.setObjectName(f"resource_{resource}_decrease")
            _make_bold(self.decrease_button)
            self.decrease_button.clicked.connect(
                lambda: self.adjusted.emit(self._resource, -1)
            )
            layout.addWidget(self.decrease_button)
        else:
            layout.addSpacing(_BUTTON_WIDTH)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setToolTip(label)
        size = icon_size or _ICON_SIZE
        pixmap = _load_pixmap(icon_path)
        if pixmap is not None:
            scaled = pixmap.scaled(
                size,
                size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.icon_label.setPixmap(scaled)
            self.icon_label.setFixedSize(size, size)
        else:
            self.icon_label.setText(label)
            self.icon_label.setMinimumWidth(_ICON_TEXT_WIDTH)

        self.value_label = QtWidgets.QLabel("-")
        self.value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.value_label.setMinimumWidth(_VALUE_MIN_WIDTH)
        self.value_label.setToolTip(label)
        self.value_label.setObjectName(f"resource_{resource}_value")

        self.increase_button: QtWidgets.QPushButton | None = None
        if adjustable:
            self.increase_button = QtWidgets.QPushButton("+")
            self.increase_button.setFixedWidth(_BUTTON_WIDTH)
            self.increase_button.setObjectName(f"resource_{resource}_increase")
            _make_bold(self.increase_button)
            self.increase_button.clicked.connect(
                lambda: self.adjusted.emit(self._resource, 1)
            )

        layout.addWidget(self.icon_label)
        layout.addWidget(self.value_label)
        if self.increase_button:
            layout.addWidget(self.increase_button)
        else:
            layout.addSpacing(_BUTTON_WIDTH)

        if emphasize:
            label_font = self.icon_label.font()
            label_font.setBold(True)
            self.icon_label.setFont(label_font)
            value_font = self.value_label.font()
            value_font.setBold(True)
            self.value_label.setFont(value_font)

    def set_value(self, value: float | int) -> None:
        self.value_label.setText(f"{value:g}")

    def set_adjust_enabled(self, enabled: bool) -> None:
        if self.decrease_button:
            self.decrease_button.setEnabled(enabled)
        if self.increase_button:
            self.increase_button.setEnabled(enabled)


class StatePanel(QtWidgets.QWidget):
    resource_adjusted = QtCore.Signal(str, int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._rows: dict[str, _ResourceRow] = {}
        for (
            resource,
            label,
            icon_name,
            adjustable,
            emphasize,
            icon_size,
        ) in _RESOURCE_ROWS:
            icon_path = _resolve_icon_path(icon_name) if icon_name else None
            row = _ResourceRow(
                resource, label, icon_path, adjustable, emphasize, icon_size, self
            )
            row.adjusted.connect(self.resource_adjusted.emit)
            layout.addWidget(row)
            self._rows[resource] = row
        layout.addStretch(1)

    def update_state(self, state: GameState) -> None:
        self._rows["case_index"].set_value(state.case_index)
        self._rows["coins"].set_value(state.coins)
        self._rows["pop"].set_value(state.pop)
        self._rows["mh"].set_value(state.mh)
        self._rows["dismissals"].set_value(state.dismissals)
        self._rows["retirement_chests"].set_value(state.retirement_chests)

    def set_adjust_enabled(self, enabled: bool) -> None:
        for row in self._rows.values():
            row.set_adjust_enabled(enabled)


def _resolve_icon_path(filename: str | None) -> Path | None:
    if not filename:
        return None
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "src" / "justice_sim" / "data" / "builtin" / "images" / filename
    return path if path.exists() else None


def _load_pixmap(path: Path | None) -> QtGui.QPixmap | None:
    if not path:
        return None
    pixmap = QtGui.QPixmap(str(path))
    return pixmap if not pixmap.isNull() else None


def _make_bold(widget: QtWidgets.QWidget) -> None:
    font = widget.font()
    font.setBold(True)
    widget.setFont(font)
