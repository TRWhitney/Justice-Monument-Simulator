"""Main window for the Qt GUI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Callable
import os
from pathlib import Path
import threading
import time

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.engine.encounter import UniformEncounterModel, select_encounter
from justice_sim.engine.effects import (
    MAIN_RESOURCES,
    NON_NEGATIVE_RESOURCES,
    apply_effects,
    resolve_expr,
)
from justice_sim.engine.reducer import (
    ActionNotAllowed,
    apply_action,
    apply_action_with_outcome,
    can_afford_action,
    is_action_blocked,
    preview_state_after_encounter_triggers,
    skip_case,
)
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import weights_for_preset
from justice_sim.models.offer import (
    BernoulliSpec,
    CategoricalSpec,
    EffectSpec,
    JusticeData,
    OfferSpec,
    OutcomeSpec,
)
from justice_sim.models.suggested_rules import SuggestedRules
from justice_sim.models.state import GameState
from justice_sim.persistence.logs import SessionLog
from justice_sim.persistence.runs import RunState, load_run_state, save_run_state
from justice_sim.planner.rollout import (
    PlannerConfig,
    PlannerRecommendation,
    RolloutPlanner,
)
from justice_sim.ui_qt.prefs import (
    load_tour_seen,
    load_ui_prefs,
    save_tour_seen,
    save_ui_prefs,
)
from justice_sim.ui_qt.widgets.log_panel import LogPanel
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget
from justice_sim.ui_qt.widgets.state_panel import StatePanel
from justice_sim.ui_qt.widgets.suggestion_panel import SuggestionPanel
from justice_sim.ui_qt.widgets.toast_area import ToastArea
from justice_sim.ui_qt.widgets.tour_panel import TourPanel, TourStartDialog
from justice_sim.ui_qt.widgets.resource_delta import format_resource_delta_html
from justice_sim.ui_qt.ui_scale import (
    UI_SCALE_MODES,
    UI_SCALE_LABELS,
    next_ui_scale,
    resolve_ui_scale,
    scale_int,
)
from justice_sim.util import expr as expr_util
from justice_sim.util.render import summarize_outcome


class TitleBar(QtWidgets.QWidget):
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


@dataclass(frozen=True)
class _TourStep:
    title: str
    body: str
    target: Callable[[], QtWidgets.QWidget | None] | None = None
    preferred_positions: tuple[str, ...] = ("right", "left", "bottom", "top")
    setup: Callable[[], None] | None = None


class _TourHighlight(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._ui_scale = 1.0
        self._dark = False
        self.setObjectName("tour_highlight")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(16)
        self._shadow.setOffset(0, 0)
        self.setGraphicsEffect(self._shadow)
        self.set_theme(False)
        self.set_ui_scale(1.0)

    def set_theme(self, dark: bool) -> None:
        self._dark = dark
        color = "#f2b153" if dark else "#c2792a"
        border = scale_int(2, self._ui_scale, minimum=1)
        radius = scale_int(10, self._ui_scale, minimum=2)
        self.setStyleSheet(
            "QFrame#tour_highlight {"
            f" border: {border}px solid {color};"
            f" border-radius: {radius}px;"
            " background: transparent;"
            "}"
        )
        shadow_color = QtGui.QColor(242, 177, 83, 140)
        self._shadow.setColor(shadow_color)

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = scale
        self._shadow.setBlurRadius(scale_int(16, scale))
        self.set_theme(self._dark)


def _is_titlebar_button(widget: QtWidgets.QWidget | None) -> bool:
    current = widget
    while current is not None:
        if isinstance(current, QtWidgets.QAbstractButton):
            return True
        current = current.parentWidget()
    return False


_RESOURCE_ICON_FILES = {
    "coins": "court_coin.png",
    "pop": "pop.png",
    "mh": "mental_health.png",
    "dismissals": "dismissal.png",
    "retirement_chests": "chest.png",
}
_RESOURCE_ICON_SIZE = 18
_RESOURCE_ICON_SPACING = 4


def _resolve_resource_icon_path(resource: str) -> Path | None:
    filename = _RESOURCE_ICON_FILES.get(resource)
    if not filename:
        return None
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "src" / "justice_sim" / "data" / "builtin" / "images" / filename
    return path if path.exists() else None


class _OutcomeChoiceDialog(QtWidgets.QDialog):
    def __init__(
        self,
        choices: list[dict[str, object]],
        *,
        dark: bool,
        ui_scale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._choices = choices
        self._ui_scale = ui_scale
        self._selected_index: int | None = None
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        root_layout = QtWidgets.QVBoxLayout(self)
        margin = scale_int(14, ui_scale)
        root_layout.setContentsMargins(margin, margin, margin, margin)

        panel = QtWidgets.QFrame()
        panel.setObjectName("outcome_dialog_panel")
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_margin = scale_int(16, ui_scale)
        panel_layout.setContentsMargins(
            panel_margin, panel_margin, panel_margin, panel_margin
        )
        panel_layout.setSpacing(scale_int(12, ui_scale))
        root_layout.addWidget(panel)

        self._shadow = QtWidgets.QGraphicsDropShadowEffect(panel)
        self._shadow.setBlurRadius(scale_int(22, ui_scale))
        self._shadow.setOffset(0, scale_int(5, ui_scale))
        panel.setGraphicsEffect(self._shadow)

        title = QtWidgets.QLabel("Choose what happened")
        title.setStyleSheet(
            f"font-weight: 700; font-size: {scale_int(14, ui_scale)}px;"
        )
        panel_layout.addWidget(title)

        self._combo = QtWidgets.QComboBox()
        self._combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        max_icons = max(
            (len(choice.get("resources", [])) for choice in choices), default=1
        )
        icon_size = scale_int(_RESOURCE_ICON_SIZE, ui_scale, minimum=1)
        icon_spacing = scale_int(_RESOURCE_ICON_SPACING, ui_scale)
        icon_width = icon_size * max_icons + icon_spacing * (max_icons - 1)
        self._combo.setIconSize(QtCore.QSize(icon_width, icon_size))
        for choice in choices:
            summary = str(choice.get("display") or choice.get("summary") or "")
            resources = list(choice.get("resources", []))
            icon = self._build_resource_icon(
                resources, icon_width, icon_size, icon_spacing
            )
            self._combo.addItem(icon, summary)
        panel_layout.addWidget(self._combo)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._accept_choice)
        button_box.rejected.connect(self.reject)
        panel_layout.addWidget(button_box)

        self._apply_theme(panel, dark)

    @property
    def selected_index(self) -> int | None:
        return self._selected_index

    def _apply_theme(self, panel: QtWidgets.QFrame, dark: bool) -> None:
        if dark:
            palette = {
                "panel_top": "#2e2e2e",
                "panel_bottom": "#1f1f1f",
                "border": "#3a3a3a",
                "field_bg": "#262626",
                "btn_bg": "#2c2c2c",
                "btn_hover": "#3a3a3a",
                "btn_pressed": "#4a4a4a",
                "fg": "#e6e6e6",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 190))
        else:
            palette = {
                "panel_top": "#fff8ee",
                "panel_bottom": "#efe1cc",
                "border": "#d8d2c3",
                "field_bg": "#ffffff",
                "btn_bg": "#f4efe6",
                "btn_hover": "#e5dccb",
                "btn_pressed": "#d6c7b0",
                "fg": "#1b1b1b",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        sizes = {
            "border_w": max(1, scale_int(1, self._ui_scale)),
            "panel_radius": scale_int(12, self._ui_scale),
            "field_radius": scale_int(6, self._ui_scale),
            "field_pad_v": scale_int(4, self._ui_scale),
            "field_pad_h": scale_int(8, self._ui_scale),
            "btn_pad_h": scale_int(10, self._ui_scale),
        }
        panel.setStyleSheet(
            (
                "QFrame#outcome_dialog_panel {{"
                " background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 {panel_top}, stop:1 {panel_bottom});"
                " border-radius: {panel_radius}px;"
                " color: {fg};"
                "}}"
                "QFrame#outcome_dialog_panel QLabel {{"
                " background: transparent;"
                " color: {fg};"
                "}}"
                "QComboBox {{"
                " background-color: {field_bg};"
                " border: {border_w}px solid {border};"
                " border-radius: {field_radius}px;"
                " padding: {field_pad_v}px {field_pad_h}px;"
                "}}"
                "QComboBox QAbstractItemView {{"
                " background-color: {field_bg};"
                " color: {fg};"
                " selection-background-color: {btn_hover};"
                "}}"
                "QComboBox::drop-down {{ border: none; }}"
                "QSpinBox {{"
                " background-color: {field_bg};"
                " border: {border_w}px solid {border};"
                " border-radius: {field_radius}px;"
                " padding: {field_pad_v}px {field_pad_h}px;"
                "}}"
                "QSpinBox::up-button, QSpinBox::down-button {{"
                " width: {field_pad_h}px;"
                "}}"
                "QPushButton {{"
                " background-color: {btn_bg};"
                " border: {border_w}px solid {border};"
                " border-radius: {field_radius}px;"
                " padding: {field_pad_v}px {btn_pad_h}px;"
                "}}"
                "QPushButton:hover {{ background-color: {btn_hover}; }}"
                "QPushButton:pressed {{ background-color: {btn_pressed}; }}"
            ).format(**palette, **sizes)
        )

    def _build_resource_icon(
        self,
        resources: list[str],
        width: int,
        icon_size: int,
        icon_spacing: int,
    ) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(width, icon_size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        x = 0
        for resource in resources:
            path = _resolve_resource_icon_path(resource)
            if not path:
                continue
            icon_pix = QtGui.QPixmap(str(path)).scaled(
                icon_size,
                icon_size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(x, 0, icon_pix)
            x += icon_size + icon_spacing
        painter.end()
        return QtGui.QIcon(pixmap)

    def _accept_choice(self) -> None:
        self._selected_index = self._combo.currentIndex()
        self.accept()


class _OutcomeValueDialog(QtWidgets.QDialog):
    def __init__(
        self,
        title: str,
        label: str,
        min_value: int,
        max_value: int,
        *,
        dark: bool,
        ui_scale: float = 1.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ui_scale = ui_scale
        self._selected_value: int | None = None
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        root_layout = QtWidgets.QVBoxLayout(self)
        margin = scale_int(14, ui_scale)
        root_layout.setContentsMargins(margin, margin, margin, margin)

        panel = QtWidgets.QFrame()
        panel.setObjectName("outcome_dialog_panel")
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_margin = scale_int(16, ui_scale)
        panel_layout.setContentsMargins(
            panel_margin, panel_margin, panel_margin, panel_margin
        )
        panel_layout.setSpacing(scale_int(12, ui_scale))
        root_layout.addWidget(panel)

        self._shadow = QtWidgets.QGraphicsDropShadowEffect(panel)
        self._shadow.setBlurRadius(scale_int(22, ui_scale))
        self._shadow.setOffset(0, scale_int(5, ui_scale))
        panel.setGraphicsEffect(self._shadow)

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(
            f"font-weight: 700; font-size: {scale_int(14, ui_scale)}px;"
        )
        title_label.setWordWrap(True)
        panel_layout.addWidget(title_label)

        body = QtWidgets.QLabel(label)
        body.setWordWrap(True)
        panel_layout.addWidget(body)

        self._spin = QtWidgets.QSpinBox()
        self._spin.setRange(min_value, max_value)
        self._spin.setValue(min_value)
        self._spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self._spin)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._accept_value)
        button_box.rejected.connect(self.reject)
        panel_layout.addWidget(button_box)

        self._apply_theme(panel, dark)

    @property
    def selected_value(self) -> int | None:
        return self._selected_value

    def _apply_theme(self, panel: QtWidgets.QFrame, dark: bool) -> None:
        if dark:
            palette = {
                "panel_top": "#2e2e2e",
                "panel_bottom": "#1f1f1f",
                "border": "#3a3a3a",
                "field_bg": "#262626",
                "btn_bg": "#2c2c2c",
                "btn_hover": "#3a3a3a",
                "btn_pressed": "#4a4a4a",
                "fg": "#e6e6e6",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 190))
        else:
            palette = {
                "panel_top": "#fff8ee",
                "panel_bottom": "#efe1cc",
                "border": "#d8d2c3",
                "field_bg": "#ffffff",
                "btn_bg": "#f4efe6",
                "btn_hover": "#e5dccb",
                "btn_pressed": "#d6c7b0",
                "fg": "#1b1b1b",
            }
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        sizes = {
            "border_w": max(1, scale_int(1, self._ui_scale)),
            "panel_radius": scale_int(12, self._ui_scale),
            "field_radius": scale_int(6, self._ui_scale),
            "field_pad_v": scale_int(4, self._ui_scale),
            "field_pad_h": scale_int(8, self._ui_scale),
            "btn_pad_h": scale_int(10, self._ui_scale),
        }
        panel.setStyleSheet(
            (
                "QFrame#outcome_dialog_panel {{"
                " background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                " stop:0 {panel_top}, stop:1 {panel_bottom});"
                " border-radius: {panel_radius}px;"
                " color: {fg};"
                "}}"
                "QLabel {{ background: transparent; color: {fg}; }}"
                "QSpinBox {{"
                " background-color: {field_bg};"
                " border: {border_w}px solid {border};"
                " border-radius: {field_radius}px;"
                " padding: {field_pad_v}px {field_pad_h}px;"
                "}}"
                "QSpinBox::up-button, QSpinBox::down-button {{"
                " width: {field_pad_h}px;"
                "}}"
                "QPushButton {{"
                " background-color: {btn_bg};"
                " border: {border_w}px solid {border};"
                " border-radius: {field_radius}px;"
                " padding: {field_pad_v}px {btn_pad_h}px;"
                "}}"
                "QPushButton:hover {{ background-color: {btn_hover}; }}"
                "QPushButton:pressed {{ background-color: {btn_pressed}; }}"
            ).format(**palette, **sizes)
        )

    def _accept_value(self) -> None:
        self._selected_value = self._spin.value()
        self.accept()


class _PlannerCancelled(RuntimeError):
    """Raised inside the planner thread when a newer request supersedes it."""


class GuiSession:
    def __init__(self, data: JusticeData) -> None:
        self.data = data
        self.state = self._build_starting_state()
        self.rng = Rng()
        self.log = SessionLog()

    def reset(self, *, reseed: bool = True) -> None:
        previous_seed = self.rng.seed
        self.state = self._build_starting_state()
        self.log = SessionLog()
        if reseed:
            new_rng = Rng()
            while new_rng.seed == previous_seed:
                new_rng = Rng()
            self.rng = new_rng
        else:
            self.rng = Rng(previous_seed)

    def _build_starting_state(self) -> GameState:
        return GameState(
            case_index=1,
            coins=5,
            pop=3,
            mh=1,
            dismissals=0,
            retirement_chests=0,
        )

    def apply(self, offer: OfferSpec, action: str) -> None:
        pre_state = self.state
        new_state, random_label = apply_action(
            self.state, offer, action, self.data, self.rng
        )
        self.log.record(
            pre_state, offer.id, action, self.rng.state(), new_state, random_label
        )
        self.state = new_state

    def skip(self, offer: OfferSpec | None = None) -> None:
        pre_state = self.state
        new_state = skip_case(self.state, self.data, self.rng)
        offer_id = offer.id if offer else "skip"
        self.log.record(pre_state, offer_id, "skip", self.rng.state(), new_state)
        self.state = new_state

    def apply_with_outcome(
        self,
        offer: OfferSpec,
        action: str,
        outcome: OutcomeSpec,
        random_label: str | None,
    ) -> None:
        pre_state = self.state
        new_state, chosen_label = apply_action_with_outcome(
            self.state,
            offer,
            action,
            outcome,
            self.data,
            self.rng,
            random_label=random_label,
        )
        self.log.record(
            pre_state, offer.id, action, self.rng.state(), new_state, chosen_label
        )
        self.state = new_state

    def undo(self) -> None:
        previous = self.log.undo()
        if previous is not None:
            self.state = previous
            if self.log.entries:
                self.rng = Rng.from_state(self.log.entries[-1].rng_state)
            else:
                self.rng = Rng(self.rng.seed)


class MainWindow(QtWidgets.QMainWindow):
    planner_progress_signal = QtCore.Signal()
    planner_progress_value_signal = QtCore.Signal(int)

    def __init__(
        self,
        data: JusticeData,
        suggested_rules: SuggestedRules | None = None,
        *,
        theme_override: bool | None = None,
        ui_scale_override: str | None = None,
        prompt_tour: bool = False,
    ) -> None:
        super().__init__()
        self.data = data
        self.session = GuiSession(data)
        self.planner = RolloutPlanner.from_defaults(
            data, suggested_rules=suggested_rules
        )
        self.encounter_model = UniformEncounterModel()
        self.current_offer: OfferSpec | None = None
        self.current_recommendation: PlannerRecommendation | None = None
        self._planner_generation = 0
        self._planner_thread: threading.Thread | None = None
        self._planner_cancel_event: threading.Event | None = None
        self._planner_result_lock = threading.Lock()
        self._planner_result_generation: int | None = None
        self._planner_result: PlannerRecommendation | None = None
        self._planner_result_error: str | None = None
        self._planner_result_cancelled = False
        self._planner_progress_lock = threading.Lock()
        self._planner_progress_value = 0
        self._planner_progress_total_value: int | None = None
        self._planner_progress_timer = QtCore.QTimer(self)
        self._planner_progress_timer.setInterval(125)
        self._planner_progress_timer.timeout.connect(self._tick_planner_progress)
        self._planner_progress_pending = False
        self._manual_adjust_pre_state: GameState | None = None
        self._manual_adjust_timer = QtCore.QTimer(self)
        self._manual_adjust_timer.setSingleShot(True)
        self._manual_adjust_timer.setInterval(350)
        self._manual_adjust_timer.timeout.connect(self._commit_manual_adjust_log)
        self.planner_progress_signal.connect(
            self._tick_planner_progress, QtCore.Qt.ConnectionType.QueuedConnection
        )
        self.planner_progress_value_signal.connect(
            self._on_planner_progress_value, QtCore.Qt.ConnectionType.QueuedConnection
        )
        self._dark_mode = False
        self._ui_scale_mode = "auto"
        self._ui_scale_factor = 1.0
        self._theme_override = theme_override
        self._ui_scale_override = ui_scale_override
        self._force_tour_prompt = prompt_tour
        self._tour_seen = False
        app = QtWidgets.QApplication.instance()
        self._base_app_font = app.font() if app is not None else self.font()
        self._base_font_point_size = (
            self._base_app_font.pointSizeF()
            if self._base_app_font.pointSizeF() > 0
            else float(self._base_app_font.pointSize() or 10)
        )
        self._settings = QtCore.QSettings() if self._settings_enabled() else None
        self._load_ui_preferences()
        self._auto_offer_id: str | None = None
        self._auto_offer_case: int | None = None
        self._tour_steps: list[_TourStep] = self._build_tour_steps()
        self._tour_index = 0
        self._tour_active = False
        self._tour_prompt_shown = False
        self._tour_prompt: TourStartDialog | None = None
        self._tour_applied_action = False

        self.setWindowTitle("Justice Monument Simulator")
        self.setMinimumSize(1200, 800)
        self.resize(1540, 900)
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        central = QtWidgets.QWidget()
        central.setObjectName("root_container")
        self.setCentralWidget(central)
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar(self.windowTitle(), self)
        root_layout.addWidget(self.title_bar)

        content = QtWidgets.QWidget()
        root_layout.addWidget(content, 1)

        layout = QtWidgets.QHBoxLayout(content)

        left_column = QtWidgets.QVBoxLayout()
        center_column = QtWidgets.QVBoxLayout()
        right_column = QtWidgets.QVBoxLayout()

        layout.addLayout(left_column, 1)
        layout.addLayout(center_column, 2)
        layout.addLayout(right_column, 1)

        self.state_panel = StatePanel()
        self.state_panel.resource_adjusted.connect(self._adjust_resource)
        left_column.addWidget(self.state_panel)

        self.risk_combo = QtWidgets.QComboBox()
        self.risk_combo.addItems(["safe", "balanced", "greedy"])
        self.risk_combo.setCurrentText(self.planner.config.risk_preset)
        self.risk_combo.currentTextChanged.connect(self._update_planner_settings)

        self.horizon_spin = QtWidgets.QSpinBox()
        self.horizon_spin.setRange(1, 100)
        self.horizon_spin.setValue(self.planner.config.horizon_cases)
        self.horizon_spin.valueChanged.connect(self._update_planner_settings)

        self.rollouts_spin = QtWidgets.QSpinBox()
        self.rollouts_spin.setRange(10, 20000)
        self.rollouts_spin.setValue(self.planner.config.rollouts_per_action)
        self.rollouts_spin.valueChanged.connect(self._update_planner_settings)

        self._sim_mode = "mid"
        self.sim_full_radio = QtWidgets.QRadioButton("Full")
        self.sim_mid_radio = QtWidgets.QRadioButton("Mid")
        self.sim_none_radio = QtWidgets.QRadioButton("None")
        self.sim_mid_radio.setChecked(True)
        self.sim_full_radio.setToolTip(
            "Auto-roll random outcomes and auto-pick offers."
        )
        self.sim_mid_radio.setToolTip(
            "Manual random outcomes with recommendations enabled."
        )
        self.sim_none_radio.setToolTip(
            "Manual outcomes and no recommendations or simulations."
        )
        self.sim_full_radio.toggled.connect(
            lambda checked: self._on_sim_mode_changed("full", checked)
        )
        self.sim_mid_radio.toggled.connect(
            lambda checked: self._on_sim_mode_changed("mid", checked)
        )
        self.sim_none_radio.toggled.connect(
            lambda checked: self._on_sim_mode_changed("none", checked)
        )
        sim_mode_row = QtWidgets.QHBoxLayout()
        sim_mode_row.setSpacing(8)
        sim_mode_row.addWidget(self.sim_full_radio)
        sim_mode_row.addWidget(self.sim_mid_radio)
        sim_mode_row.addWidget(self.sim_none_radio)
        sim_mode_container = QtWidgets.QWidget()
        sim_mode_container.setLayout(sim_mode_row)

        settings_group = QtWidgets.QGroupBox("Planner Settings")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.addRow("Risk", self.risk_combo)
        settings_layout.addRow("Horizon", self.horizon_spin)
        settings_layout.addRow("Rollouts", self.rollouts_spin)
        settings_layout.addRow("Sim Mode", sim_mode_container)
        left_column.addWidget(settings_group)
        self._planner_settings_group = settings_group
        self._sim_mode_container = sim_mode_container

        self.import_button = QtWidgets.QPushButton("Import Run")
        self.export_button = QtWidgets.QPushButton("Export Run")
        self.reset_button = QtWidgets.QPushButton("Reset Run")
        self.reset_button.setObjectName("reset_run_button")
        self.import_button.clicked.connect(self._import_run)
        self.export_button.clicked.connect(self._export_run)
        self.reset_button.clicked.connect(self._reset_run)
        left_column.addWidget(self.import_button)
        left_column.addWidget(self.export_button)
        left_column.addWidget(self.reset_button)

        self.toast_area = ToastArea()
        left_column.addWidget(self.toast_area)
        left_column.addStretch(1)

        self.offer_search = OfferSearchWidget(data, self.session.state)
        self.offer_search.offer_selected.connect(self._on_offer_selected)
        center_column.addWidget(self.offer_search)

        self.suggestion_panel = SuggestionPanel()
        right_column.addWidget(self.suggestion_panel)

        self.approve_button = QtWidgets.QPushButton("Approve")
        self.reject_button = QtWidgets.QPushButton("Reject")
        self.dismiss_button = QtWidgets.QPushButton("Dismiss")
        self.skip_button = QtWidgets.QPushButton("Skip")
        self.best_button = QtWidgets.QPushButton("Apply Recommended")
        self.game_over_label = QtWidgets.QLabel("Game Over")
        self.game_over_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.game_over_label.setStyleSheet(
            "color: #b00020; font-weight: 700; font-size: 18px;"
        )
        self.game_over_label.hide()

        self.approve_button.clicked.connect(lambda: self._apply_action("approve"))
        self.reject_button.clicked.connect(lambda: self._apply_action("reject"))
        self.dismiss_button.clicked.connect(lambda: self._apply_action("dismiss"))
        self.skip_button.clicked.connect(self._skip_case)
        self.best_button.clicked.connect(self._apply_best)

        hotkeys = {
            "approve": "Ctrl+Shift+A",
            "reject": "Ctrl+Shift+R",
            "dismiss": "Ctrl+Shift+D",
            "skip": "Ctrl+Shift+S",
            "best": "Ctrl+Shift+B",
            "undo": "Ctrl+Z",
        }
        self.approve_button.setText(f"Approve ({hotkeys['approve']})")
        self.reject_button.setText(f"Reject ({hotkeys['reject']})")
        self.dismiss_button.setText(f"Dismiss ({hotkeys['dismiss']})")
        self.skip_button.setText(f"Skip ({hotkeys['skip']})")
        self.best_button.setText(f"Apply Recommended ({hotkeys['best']})")
        self._shortcuts: list[QtGui.QShortcut] = []
        self._shortcuts.append(
            self._make_shortcut(
                hotkeys["approve"], lambda: self._apply_action("approve")
            )
        )
        self._shortcuts.append(
            self._make_shortcut(hotkeys["reject"], lambda: self._apply_action("reject"))
        )
        self._shortcuts.append(
            self._make_shortcut(
                hotkeys["dismiss"], lambda: self._apply_action("dismiss")
            )
        )
        self._shortcuts.append(self._make_shortcut(hotkeys["skip"], self._skip_case))
        self._shortcuts.append(self._make_shortcut(hotkeys["best"], self._apply_best))
        self._shortcuts.append(self._make_shortcut(hotkeys["undo"], self._undo))

        right_column.addWidget(self.approve_button)
        right_column.addWidget(self.reject_button)
        right_column.addWidget(self.dismiss_button)
        right_column.addWidget(self.skip_button)
        right_column.addWidget(self.best_button)
        right_column.addWidget(self.game_over_label)

        self.log_panel = LogPanel(data)
        self.log_panel.undo_requested.connect(self._undo)
        self.log_panel.undo_button.setText(f"Undo ({hotkeys['undo']})")
        right_column.addWidget(self.log_panel)

        self.theme_toggle = QtWidgets.QToolButton(self)
        self.theme_toggle.setCheckable(True)
        self.theme_toggle.setAutoRaise(True)
        self.theme_toggle.setText("☀")
        self.theme_toggle.setToolTip("Light theme")
        self.theme_toggle.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.theme_toggle.toggled.connect(self._on_theme_toggled)
        self.scale_toggle = QtWidgets.QToolButton(self)
        self.scale_toggle.setAutoRaise(True)
        self.scale_toggle.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.scale_toggle.setAccessibleName("UI scale")
        self.scale_toggle.clicked.connect(self._on_scale_toggled)
        self._size_grip = QtWidgets.QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)
        self._tour_highlight = _TourHighlight(self)
        self._tour_highlight.hide()
        self.tour_panel = TourPanel(self)
        self.tour_panel.hide()
        self.tour_panel.next_requested.connect(self._on_tour_next)
        self.tour_panel.back_requested.connect(self._on_tour_back)
        self.tour_panel.close_requested.connect(self._dismiss_tour)
        self._update_window_controls_geometry()

        self._sync_theme_toggle()
        self._apply_ui_scale()
        self.title_bar.set_maximized(self.isMaximized())
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._refresh()

    def _refresh(self) -> None:
        self._sync_auto_offer()
        self.state_panel.update_state(self.session.state)
        self.state_panel.set_adjust_enabled(True)
        self.log_panel.update_log(self.session.log)
        self.offer_search.set_auto_offer_id(self._auto_offer_id)
        self.offer_search.set_show_all_visible(self._sim_mode != "full")
        self.offer_search.update_state(self.session.state, preserve_scroll=True)
        self._update_action_controls()
        if self._planner_progress_timer.isActive():
            self._tick_planner_progress()
        elif self.current_recommendation:
            self.suggestion_panel.update_recommendation(self.current_recommendation)

    def changeEvent(self, event: QtCore.QEvent) -> None:
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if not self._tour_prompt_shown and self._should_prompt_tour():
            QtCore.QTimer.singleShot(0, self._prompt_tour_start)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.KeyPress and isinstance(
            event, QtGui.QKeyEvent
        ):
            if self._should_focus_search_on_keypress(obj, event):
                if self.offer_search.focus_search_input(event.text()):
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _should_focus_search_on_keypress(
        self, obj: QtCore.QObject, event: QtGui.QKeyEvent
    ) -> bool:
        if not self.isActiveWindow():
            return False
        active_window = QtWidgets.QApplication.activeWindow()
        if active_window is not None and active_window is not self:
            return False
        if isinstance(obj, QtWidgets.QWidget):
            if obj is not self and not self.isAncestorOf(obj):
                return False
        focus_widget = self.focusWidget()
        if focus_widget is not None and self._is_input_widget(focus_widget):
            return False
        modifiers = event.modifiers()
        if modifiers & (
            QtCore.Qt.KeyboardModifier.ControlModifier
            | QtCore.Qt.KeyboardModifier.AltModifier
            | QtCore.Qt.KeyboardModifier.MetaModifier
        ):
            return False
        text = event.text()
        if not text or not text.strip():
            return False
        if not text.isprintable():
            return False
        return self.offer_search.can_accept_typed_input()

    def _is_input_widget(self, widget: QtWidgets.QWidget) -> bool:
        return isinstance(
            widget,
            (
                QtWidgets.QLineEdit,
                QtWidgets.QTextEdit,
                QtWidgets.QPlainTextEdit,
                QtWidgets.QAbstractSpinBox,
                QtWidgets.QComboBox,
            ),
        )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_window_controls_geometry()

    def _on_theme_toggled(self, checked: bool) -> None:
        self._dark_mode = checked
        if checked:
            self.theme_toggle.setText("☾")
            self.theme_toggle.setToolTip("Dark theme")
        else:
            self.theme_toggle.setText("☀")
            self.theme_toggle.setToolTip("Light theme")
        self._apply_theme(self._dark_mode)
        self._update_scale_toggle_visuals()
        self._save_ui_preferences()

    def _on_scale_toggled(self) -> None:
        self._ui_scale_mode = next_ui_scale(self._ui_scale_mode)
        self._apply_ui_scale()
        self._save_ui_preferences()

    def _on_sim_mode_changed(self, mode: str, checked: bool) -> None:
        if not checked:
            return
        previous = self._sim_mode
        if previous == mode:
            return
        self._sim_mode = mode
        if previous == "full" and mode != "full":
            self._auto_offer_id = None
            self._auto_offer_case = None
        if mode == "none":
            self._stop_planner_thread()
            self.current_recommendation = None
            self._clear_recommendation_ui()
        elif self.current_offer:
            self.current_recommendation = None
            self.suggestion_panel.best_label.setText("Calculating...")
            self.suggestion_panel.metrics_label.setText("")
            self.suggestion_panel.set_calculating(
                True, self._planner_progress_total(self.current_offer)
            )
            self._start_planner(self.current_offer)
        self._refresh()

    def _apply_ui_scale(self) -> None:
        scale = resolve_ui_scale(self._ui_scale_mode, dpi=self._logical_dpi())
        self._ui_scale_factor = scale
        app = QtWidgets.QApplication.instance()
        if app is not None:
            font = QtGui.QFont(self._base_app_font)
            if self._base_font_point_size > 0:
                font.setPointSizeF(self._base_font_point_size * scale)
            else:
                base_px = self._base_app_font.pixelSize() or 12
                font.setPixelSize(scale_int(base_px, scale, minimum=1))
            app.setFont(font)
        self.title_bar.set_ui_scale(scale)
        self.state_panel.set_ui_scale(scale)
        self.offer_search.set_ui_scale(scale)
        self.log_panel.set_ui_scale(scale)
        self.toast_area.set_ui_scale(scale)
        self.tour_panel.set_ui_scale(scale)
        self._tour_highlight.set_ui_scale(scale)
        if self._tour_prompt is not None:
            self._tour_prompt.set_ui_scale(scale)
        self._size_grip.setFixedSize(
            self._scaled(16, minimum=1), self._scaled(16, minimum=1)
        )
        self.game_over_label.setStyleSheet(
            "color: #b00020; font-weight: 700; "
            f"font-size: {self._scaled(18, minimum=1)}px;"
        )
        self._apply_theme(self._dark_mode)
        self._update_scale_toggle_visuals()

    def _logical_dpi(self) -> float | None:
        screen = self.screen()
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        return screen.logicalDotsPerInch() if screen is not None else None

    def _scaled(self, value: int, *, minimum: int | None = None) -> int:
        return scale_int(value, self._ui_scale_factor, minimum=minimum)

    def _resource_icon_size(self) -> int:
        return self._scaled(_RESOURCE_ICON_SIZE, minimum=1)

    def _ensure_offer_selected(self) -> None:
        if self.offer_search.results_list.count() == 0:
            self.offer_search._on_search(self.offer_search.search_input.text())
        if self.offer_search.results_list.count() == 0:
            return
        self.offer_search.results_list.setCurrentRow(0)
        self.offer_search._on_selection()

    def _ensure_action_applied(self) -> None:
        if self._tour_applied_action:
            return
        self._ensure_offer_selected()
        offer = self.current_offer
        if offer is None:
            return
        action = None
        if "approve" in offer.actions_available:
            action = "approve"
        elif "reject" in offer.actions_available:
            action = "reject"
        elif "dismiss" in offer.actions_available:
            action = "dismiss"
        if action is None:
            return
        pre_state = self.session.state
        try:
            self.session.apply(offer, action)
        except ActionNotAllowed:
            return
        self.toast_area.show_toast(
            format_resource_delta_html(
                pre_state,
                self.session.state,
                icon_size=self._resource_icon_size(),
            )
        )
        self.current_recommendation = None
        self._clear_recommendation_ui()
        self._tour_applied_action = True
        self._refresh()

    def _build_tour_steps(self) -> list[_TourStep]:
        return [
            _TourStep(
                title="Welcome to Justice Monument Simulator",
                body=(
                    "This tour highlights the main features and shows where to "
                    "interact. Use Next to continue or Skip Tour to dismiss. "
                    "You can always explore freely after the tour ends."
                ),
            ),
            _TourStep(
                title="Search offers",
                body=(
                    "Type to search NPCs, titles, or offer text. "
                    "Use #npc or #npc_name_with_underscores to filter by NPC, "
                    "and $term to filter by effect text."
                ),
                target=lambda: self.offer_search.search_input,
                preferred_positions=("bottom", "right", "left", "top"),
            ),
            _TourStep(
                title="NPC filters",
                body=(
                    "Click an NPC icon to filter offers by that character. "
                    "Icons dim when a filter is active, making matches stand out."
                ),
                target=lambda: self.offer_search._npc_filter_bar,
                preferred_positions=("bottom", "right", "left", "top"),
            ),
            _TourStep(
                title="Show all toggle",
                body=(
                    "Use this toggle to ignore offer conditions when browsing. "
                    "It’s handy when you want to read ahead or debug offer chains."
                ),
                target=lambda: self.offer_search.show_all_toggle,
                preferred_positions=("bottom", "right", "left", "top"),
            ),
            _TourStep(
                title="Offer list",
                body=(
                    "Browse offers here and click one to select it. "
                    "Each card summarizes the approve/reject effects."
                ),
                target=lambda: self.offer_search.results_list,
                preferred_positions=("right", "left", "bottom", "top"),
            ),
            _TourStep(
                title="Select an offer",
                body=(
                    "We’ll select an offer to enable actions and recommendations. "
                    "Selection also drives what appears in the suggestion panel."
                ),
                target=lambda: self.offer_search.results_list,
                preferred_positions=("right", "left", "bottom", "top"),
                setup=self._ensure_offer_selected,
            ),
            _TourStep(
                title="Recommendations",
                body=(
                    "The suggestion panel shows the best action and expected metrics. "
                    "It updates as state changes or settings are adjusted."
                ),
                target=lambda: self.suggestion_panel,
                preferred_positions=("left", "bottom", "top", "right"),
                setup=self._ensure_offer_selected,
            ),
            _TourStep(
                title="Action buttons",
                body=(
                    "Apply actions here once an offer is selected. "
                    "Buttons enable/disable based on affordability and rules."
                ),
                target=lambda: self.approve_button,
                preferred_positions=("left", "top", "bottom", "right"),
                setup=self._ensure_offer_selected,
            ),
            _TourStep(
                title="Apply an action",
                body=(
                    "We’ll apply an action to add an entry to the log. "
                    "This simulates a real decision so you can see the flow."
                ),
                target=lambda: self.approve_button,
                preferred_positions=("left", "top", "bottom", "right"),
                setup=self._ensure_action_applied,
            ),
            _TourStep(
                title="State panel",
                body=(
                    "These resources update after every action. "
                    "Use the +/- controls to adjust the starting state."
                ),
                target=lambda: self.state_panel,
                preferred_positions=("right", "bottom", "top", "left"),
            ),
            _TourStep(
                title="Planner settings",
                body=(
                    "Tune risk, horizon, rollouts, and sim mode here. "
                    "These settings change how recommendations are calculated."
                ),
                target=lambda: self._planner_settings_group,
                preferred_positions=("right", "bottom", "top", "left"),
            ),
            _TourStep(
                title="Session log",
                body=(
                    "Your action history appears here with details on hover. "
                    "Hover entries to see the offer card and effects."
                ),
                target=lambda: self.log_panel,
                preferred_positions=("left", "top", "bottom", "right"),
                setup=self._ensure_action_applied,
            ),
            _TourStep(
                title="Theme + UI scale",
                body=(
                    "Toggle theme and UI scale here for comfort. "
                    "These preferences persist between launches."
                ),
                target=lambda: self.theme_toggle,
                preferred_positions=("top", "right", "left", "bottom"),
            ),
            _TourStep(
                title="Import and export",
                body=(
                    "Save or load runs and reset the session from these buttons. "
                    "Export is useful for sharing, resuming later, or saving "
                    "starting conditions."
                ),
                target=lambda: self.import_button,
                preferred_positions=("right", "bottom", "top", "left"),
            ),
            _TourStep(
                title="Tour complete",
                body=(
                    "That’s it! You’re ready to explore on your own. "
                    "We’ll reset the run when you finish the tour."
                ),
            ),
        ]

    def _start_tour(self) -> None:
        self._tour_index = 0
        self._tour_active = True
        self._tour_applied_action = False
        self._update_tour_panel()
        self.tour_panel.show()
        self.tour_panel.raise_()
        self._position_tour_panel()

    def _prompt_tour_start(self) -> None:
        if self._tour_prompt_shown:
            return
        self._tour_prompt_shown = True
        if self._tour_prompt is None:
            self._tour_prompt = TourStartDialog(self)
            self._tour_prompt.start_requested.connect(self._on_tour_start)
            self._tour_prompt.skip_requested.connect(self._on_tour_skip)
        self._tour_prompt.set_theme(self._dark_mode)
        self._tour_prompt.set_ui_scale(self._ui_scale_factor)
        self._position_tour_prompt()
        self._tour_prompt.show()
        self._tour_prompt.raise_()

    def _dismiss_tour(self) -> None:
        self._tour_active = False
        self.tour_panel.hide()
        self._clear_tour_highlight()

    def _on_tour_start(self) -> None:
        if self._tour_prompt is not None:
            self._tour_prompt.hide()
        self._mark_tour_seen()
        self._start_tour()

    def _on_tour_skip(self) -> None:
        if self._tour_prompt is not None:
            self._tour_prompt.hide()
        self._mark_tour_seen()
        self._dismiss_tour()

    def _on_tour_next(self) -> None:
        if self._tour_index >= len(self._tour_steps) - 1:
            self._finish_tour()
            return
        self._tour_index += 1
        self._update_tour_panel()

    def _on_tour_back(self) -> None:
        if self._tour_index <= 0:
            return
        self._tour_index -= 1
        self._update_tour_panel()

    def _finish_tour(self) -> None:
        self._mark_tour_seen()
        self._dismiss_tour()
        self._reset_run()

    def _should_prompt_tour(self) -> bool:
        if self._force_tour_prompt:
            return True
        return not self._tour_seen

    def _mark_tour_seen(self) -> None:
        if self._tour_seen:
            return
        self._tour_seen = True
        if self._settings is None:
            return
        save_tour_seen(self._settings, seen=True)

    def _update_tour_panel(self) -> None:
        if not self._tour_steps:
            self._dismiss_tour()
            return
        step = self._tour_steps[self._tour_index]
        if step.setup:
            step.setup()
        self.tour_panel.set_step(
            self._tour_index,
            len(self._tour_steps),
            step.title,
            step.body,
        )
        self.tour_panel.layout().activate()
        self.tour_panel.adjustSize()
        self.tour_panel.resize(
            self.tour_panel.width(), self.tour_panel.sizeHint().height()
        )
        self._update_tour_highlight()
        self._position_tour_panel()

    def _settings_enabled(self) -> bool:
        if os.environ.get("JUSTICE_SIM_DISABLE_SETTINGS") == "1":
            return False
        return "PYTEST_CURRENT_TEST" not in os.environ

    def _load_ui_preferences(self) -> None:
        if self._settings is not None:
            theme_dark, scale_mode = load_ui_prefs(
                self._settings,
                default_theme=self._dark_mode,
                default_scale=self._ui_scale_mode,
                allowed_modes=UI_SCALE_MODES,
            )
            self._dark_mode = theme_dark
            self._ui_scale_mode = scale_mode
            self._tour_seen = load_tour_seen(self._settings, default_seen=False)
        if self._theme_override is not None:
            self._dark_mode = self._theme_override
        if (
            self._ui_scale_override is not None
            and self._ui_scale_override in UI_SCALE_MODES
        ):
            self._ui_scale_mode = self._ui_scale_override

    def _save_ui_preferences(self) -> None:
        if self._settings is None:
            return
        save_ui_prefs(
            self._settings,
            theme_dark=self._dark_mode,
            scale_mode=self._ui_scale_mode,
        )

    def _sync_theme_toggle(self) -> None:
        blocker = QtCore.QSignalBlocker(self.theme_toggle)
        self.theme_toggle.setChecked(self._dark_mode)
        if self._dark_mode:
            self.theme_toggle.setText("☾")
            self.theme_toggle.setToolTip("Dark theme")
        else:
            self.theme_toggle.setText("☀")
            self.theme_toggle.setToolTip("Light theme")
        del blocker

    def _update_scale_toggle_visuals(self) -> None:
        label = UI_SCALE_LABELS.get(self._ui_scale_mode, "Auto")
        icon_size = self._scaled(20, minimum=1)
        icon = self._build_scale_icon(self._ui_scale_mode, icon_size)
        self.scale_toggle.setIcon(icon)
        self.scale_toggle.setIconSize(QtCore.QSize(icon_size, icon_size))
        self.scale_toggle.setToolTip(f"UI scale: {label}")

    def _build_scale_icon(self, mode: str, size: int) -> QtGui.QIcon:
        letters = {
            "auto": "A",
            "small": "S",
            "medium": "M",
            "large": "L",
        }
        text = letters.get(mode, "A")
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        if self._dark_mode:
            border = QtGui.QColor(230, 230, 230)
            text_color = QtGui.QColor(245, 245, 245)
        else:
            border = QtGui.QColor(40, 40, 40)
            text_color = QtGui.QColor(30, 30, 30)
        pen_width = max(1, int(round(size * 0.08)))
        painter.setPen(QtGui.QPen(border, pen_width))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        radius = max(2, int(round(size * 0.25)))
        rect = QtCore.QRect(
            pen_width,
            pen_width,
            size - pen_width * 2,
            size - pen_width * 2,
        )
        painter.drawRoundedRect(rect, radius, radius)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(1, int(round(size * 0.55))))
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _apply_theme(self, dark: bool) -> None:
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
                "selected": "#3a3a3a",
                "title_bg": "#242424",
                "title_hover": "rgba(255, 255, 255, 0.08)",
                "title_pressed": "rgba(255, 255, 255, 0.16)",
                "close_hover": "#a33838",
                "close_pressed": "#7a2c2c",
                "close_fg": "#ffffff",
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
                "selected": "#e5e0d6",
                "title_bg": "#f2ede2",
                "title_hover": "rgba(0, 0, 0, 0.06)",
                "title_pressed": "rgba(0, 0, 0, 0.12)",
                "close_hover": "#d86b6b",
                "close_pressed": "#b95a5a",
                "close_fg": "#ffffff",
            }
        )
        sizes = {
            "border_w": max(1, self._scaled(1)),
            "title_pad_left": self._scaled(4),
            "title_btn_pad_v": self._scaled(2),
            "title_btn_pad_h": self._scaled(6),
            "title_btn_radius": self._scaled(6, minimum=1),
            "group_radius": self._scaled(6, minimum=1),
            "group_margin_top": self._scaled(6),
            "group_title_left": self._scaled(8),
            "group_title_pad": self._scaled(4),
            "field_radius": self._scaled(4, minimum=1),
            "field_pad_v": self._scaled(2),
            "field_pad_h": self._scaled(6),
            "btn_radius": self._scaled(4, minimum=1),
            "btn_pad_v": self._scaled(4),
            "btn_pad_h": self._scaled(8),
            "tool_pad_v": self._scaled(2),
            "tool_pad_h": self._scaled(4),
        }
        self.setStyleSheet(
            (
                "QWidget {{ background-color: {bg}; color: {fg}; }}"
                "QWidget#root_container {{ border: {border_w}px solid {border}; }}"
                "QWidget#title_bar {{ background-color: {title_bg}; border-bottom: {border_w}px solid {border}; }}"
                "QLabel#title_label {{ font-weight: 600; padding-left: {title_pad_left}px; }}"
                'QToolButton[title_button="true"] {{ background: transparent; border: none;'
                " padding: {title_btn_pad_v}px {title_btn_pad_h}px; }}"
                'QToolButton[title_button="true"]:hover {{ background-color: {title_hover};'
                " border-radius: {title_btn_radius}px; }}"
                'QToolButton[title_button="true"]:pressed {{ background-color: {title_pressed};'
                " border-radius: {title_btn_radius}px; }}"
                'QToolButton[title_role="close"]:hover {{ background-color: {close_hover}; color: {close_fg}; }}'
                'QToolButton[title_role="close"]:pressed {{ background-color: {close_pressed}; color: {close_fg}; }}'
                "QGroupBox {{ border: {border_w}px solid {border}; border-radius: {group_radius}px;"
                " margin-top: {group_margin_top}px; }}"
                "QGroupBox::title {{ subcontrol-origin: margin; left: {group_title_left}px;"
                " padding: 0 {group_title_pad}px; }}"
                "QLineEdit, QSpinBox, QComboBox, QListWidget {{"
                " background-color: {field_bg}; border: {border_w}px solid {border};"
                " border-radius: {field_radius}px; padding: {field_pad_v}px {field_pad_h}px; }}"
                "QPushButton {{ background-color: {btn_bg}; border: {border_w}px solid {border};"
                " border-radius: {btn_radius}px; padding: {btn_pad_v}px {btn_pad_h}px; }}"
                "QPushButton:hover {{ background-color: {btn_hover}; }}"
                "QPushButton:pressed {{ background-color: {btn_pressed}; }}"
                "QToolButton {{ background: transparent; border: none;"
                " padding: {tool_pad_v}px {tool_pad_h}px; }}"
                "QPushButton:disabled, QToolButton:disabled {{ color: {disabled}; }}"
                "QListWidget::item:selected {{ background-color: {selected}; }}"
            ).format(**palette, **sizes)
        )
        self.toast_area.set_theme(dark)
        self.log_panel.set_theme(dark)
        self.tour_panel.set_theme(dark)
        if self._tour_prompt is not None:
            self._tour_prompt.set_theme(dark)
        self._tour_highlight.set_theme(dark)
        self._update_window_controls_geometry()

    def _update_window_controls_geometry(self) -> None:
        size = self._scaled(44, minimum=1)
        margin = self._scaled(16)
        hover_radius = self._scaled(10, minimum=1)
        toggle_style = (
            "QToolButton { border: none; background: transparent; }"
            f"QToolButton:hover {{ background-color: rgba(0, 0, 0, 20); border-radius: {hover_radius}px; }}"
            f"QToolButton:pressed {{ background-color: rgba(0, 0, 0, 40); border-radius: {hover_radius}px; }}"
        )
        self.theme_toggle.setFixedSize(size, size)
        font = self.theme_toggle.font()
        font.setPointSize(self._scaled(18, minimum=1))
        self.theme_toggle.setFont(font)
        self.theme_toggle.setStyleSheet(toggle_style)
        self.scale_toggle.setFixedSize(size, size)
        self.scale_toggle.setStyleSheet(toggle_style)
        geo = self.geometry()
        self.theme_toggle.move(margin, geo.height() - margin - size)
        spacing = self._scaled(8)
        self.scale_toggle.move(margin + size + spacing, geo.height() - margin - size)
        grip_margin = self._scaled(10)
        self._size_grip.move(
            geo.width() - grip_margin - self._size_grip.width(),
            geo.height() - grip_margin - self._size_grip.height(),
        )
        self._position_tour_panel()
        self._position_tour_prompt()
        self._update_tour_highlight()

    def _position_tour_panel(self) -> None:
        if not self.tour_panel.isVisible():
            return
        margin = self._scaled(16)
        panel_width = self.tour_panel.width() or self.tour_panel.sizeHint().width()
        panel_height = self.tour_panel.sizeHint().height()
        window_rect = QtCore.QRect(0, 0, self.width(), self.height())
        target_rect = self._tour_target_rect()
        if target_rect is None:
            x = margin
            y = self.title_bar.height() + margin
            max_x = max(margin, self.width() - panel_width - margin)
            max_y = max(margin, self.height() - panel_height - margin)
            self.tour_panel.move(min(x, max_x), min(y, max_y))
            return
        candidates: list[QtCore.QPoint] = []
        for position in self._tour_candidate_positions():
            x, y = self._tour_position_for_target(
                target_rect, panel_width, panel_height, margin, position
            )
            candidates.append(QtCore.QPoint(x, y))
        if not candidates:
            candidates = [QtCore.QPoint(margin, self.title_bar.height() + margin)]
        best = candidates[0]
        best_score = self._tour_position_score(
            best,
            panel_width,
            panel_height,
            target_rect,
            window_rect,
        )
        for candidate in candidates[1:]:
            score = self._tour_position_score(
                candidate, panel_width, panel_height, target_rect, window_rect
            )
            if score < best_score:
                best_score = score
                best = candidate
        self.tour_panel.move(best)

    def _position_tour_prompt(self) -> None:
        if self._tour_prompt is None or not self._tour_prompt.isVisible():
            return
        self._tour_prompt.adjustSize()
        prompt_size = self._tour_prompt.sizeHint()
        window_geo = self.geometry()
        center = window_geo.center()
        x = center.x() - prompt_size.width() // 2
        y = center.y() - prompt_size.height() // 2
        self._tour_prompt.move(max(0, x), max(0, y))

    def _tour_candidate_positions(self) -> tuple[str, ...]:
        if not self._tour_active:
            return ()
        step = self._tour_steps[self._tour_index]
        return step.preferred_positions

    def _tour_target_rect(self) -> QtCore.QRect | None:
        if not self._tour_active:
            return None
        step = self._tour_steps[self._tour_index]
        if step.target is None:
            return None
        target = step.target()
        if target is None or not target.isVisible():
            return None
        top_left = target.mapTo(self, QtCore.QPoint(0, 0))
        rect = QtCore.QRect(top_left, target.size())
        return rect

    def _tour_position_for_target(
        self,
        target_rect: QtCore.QRect,
        panel_width: int,
        panel_height: int,
        margin: int,
        position: str,
    ) -> tuple[int, int]:
        if position == "right":
            x = target_rect.right() + margin
            y = target_rect.top()
        elif position == "left":
            x = target_rect.left() - panel_width - margin
            y = target_rect.top()
        elif position == "top":
            x = target_rect.left()
            y = target_rect.top() - panel_height - margin
        else:  # bottom
            x = target_rect.left()
            y = target_rect.bottom() + margin
        max_x = max(margin, self.width() - panel_width - margin)
        max_y = max(margin, self.height() - panel_height - margin)
        x = min(max(margin, x), max_x)
        y = min(max(margin, y), max_y)
        return x, y

    def _tour_position_score(
        self,
        pos: QtCore.QPoint,
        panel_width: int,
        panel_height: int,
        target_rect: QtCore.QRect,
        window_rect: QtCore.QRect,
    ) -> float:
        panel_rect = QtCore.QRect(pos, QtCore.QSize(panel_width, panel_height))
        intersection = panel_rect.intersected(target_rect)
        intersection_area = intersection.width() * intersection.height()
        center_distance = (panel_rect.center().x() - target_rect.center().x()) ** 2 + (
            panel_rect.center().y() - target_rect.center().y()
        ) ** 2
        overflow = 0
        if not window_rect.contains(panel_rect):
            overflow_rect = panel_rect.adjusted(
                -window_rect.left(),
                -window_rect.top(),
                window_rect.right() - panel_rect.right(),
                window_rect.bottom() - panel_rect.bottom(),
            )
            overflow = abs(overflow_rect.left()) + abs(overflow_rect.top())
        return intersection_area * 1000 + center_distance + overflow * 10000

    def _update_tour_highlight(self) -> None:
        if not self._tour_active:
            self._tour_highlight.hide()
            return
        target_rect = self._tour_target_rect()
        if target_rect is None:
            self._tour_highlight.hide()
            return
        padding = self._scaled(6)
        highlight_rect = target_rect.adjusted(
            -padding, -padding, padding, padding
        ).intersected(QtCore.QRect(0, 0, self.width(), self.height()))
        self._tour_highlight.setGeometry(highlight_rect)
        self._tour_highlight.show()
        self._tour_highlight.raise_()
        self.tour_panel.raise_()

    def _clear_tour_highlight(self) -> None:
        self._tour_highlight.hide()

    def _make_shortcut(self, sequence: str, handler: callable) -> QtGui.QShortcut:
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(handler)
        return shortcut

    def _on_offer_selected(self, offer: OfferSpec | None) -> None:
        if offer is None:
            self.current_offer = None
            self.current_recommendation = None
            self._stop_planner_thread()
            self._clear_recommendation_ui()
            self._update_action_controls()
            return
        self.current_offer = offer
        self.current_recommendation = None
        self._update_action_controls()
        if self._sim_mode == "none":
            self._clear_recommendation_ui()
            return
        self.suggestion_panel.best_label.setText("Calculating...")
        self.suggestion_panel.metrics_label.setText("")
        self.suggestion_panel.set_calculating(True, self._planner_progress_total(offer))
        self._start_planner(offer)

    def _start_planner(self, offer: OfferSpec) -> None:
        self._planner_generation += 1
        generation = self._planner_generation
        self._stop_planner_thread()

        total = self._reset_planner_progress(offer)
        with self._planner_result_lock:
            self._planner_result_generation = None
            self._planner_result = None
            self._planner_result_error = None
            self._planner_result_cancelled = False
        cancel_event = threading.Event()
        self._planner_cancel_event = cancel_event
        progress_count = 0
        progress_last_emit_time = 0.0

        def progress(delta: int) -> None:
            nonlocal progress_count, progress_last_emit_time
            if cancel_event.is_set():
                raise _PlannerCancelled()
            self._increment_planner_progress(delta)
            progress_count += delta
            now = time.monotonic()
            total_reached = total is not None and total > 0 and progress_count >= total
            if total_reached or now - progress_last_emit_time >= 0.05:
                progress_last_emit_time = now
                if total is not None and total > 0:
                    self.planner_progress_value_signal.emit(progress_count)
                time.sleep(0)

        def run() -> None:
            try:
                recommendation = self.planner.recommend(
                    self.session.state, offer, progress=progress
                )
            except _PlannerCancelled:
                with self._planner_result_lock:
                    self._planner_result_generation = generation
                    self._planner_result_cancelled = True
                return
            except Exception as exc:  # pragma: no cover - defensive UI safety
                with self._planner_result_lock:
                    self._planner_result_generation = generation
                    self._planner_result_error = str(exc)
                return
            with self._planner_result_lock:
                self._planner_result_generation = generation
                self._planner_result = recommendation

        thread = threading.Thread(target=run, daemon=True)
        self._planner_thread = thread
        thread.start()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._stop_planner_thread()
        if self._tour_prompt is not None:
            self._tour_prompt.hide()
        super().closeEvent(event)

    def _stop_planner_thread(self) -> None:
        if not self._planner_thread:
            return
        if self._planner_cancel_event:
            self._planner_cancel_event.set()
        if isinstance(self._planner_thread, threading.Thread):
            if self._planner_thread.is_alive():
                self._planner_thread.join(timeout=0.2)
        self._planner_thread = None
        self._planner_cancel_event = None
        self._stop_planner_progress()

    def _apply_action(self, action: str) -> None:
        self._flush_manual_adjust_log()
        if not self.current_offer:
            self.toast_area.show_toast("Select an offer first.")
            return
        pre_state = self.session.state
        try:
            if self._sim_mode == "full":
                self.session.apply(self.current_offer, action)
            else:
                outcome = self._select_outcome(self.current_offer, action)
                resolved = self._resolve_outcome_randomness(outcome)
                if resolved is None:
                    self.toast_area.show_toast("Action cancelled.")
                    return
                resolved_outcome, random_label = resolved
                self.session.apply_with_outcome(
                    self.current_offer, action, resolved_outcome, random_label
                )
        except ActionNotAllowed as exc:
            self.toast_area.show_toast(f"{action.title()} failed: {exc}")
            return
        self.toast_area.show_toast(
            format_resource_delta_html(
                pre_state,
                self.session.state,
                icon_size=self._resource_icon_size(),
            )
        )
        self.current_recommendation = None
        self._clear_recommendation_ui()
        self._refresh()

    def _skip_case(self) -> None:
        self._flush_manual_adjust_log()
        pre_state = self.session.state
        try:
            self.session.skip(self.current_offer)
        except ActionNotAllowed as exc:
            self.toast_area.show_toast(f"Skip failed: {exc}")
            return
        self.toast_area.show_toast(
            format_resource_delta_html(
                pre_state,
                self.session.state,
                icon_size=self._resource_icon_size(),
                action="skip",
            )
        )
        self.current_recommendation = None
        self._clear_recommendation_ui()
        self._refresh()

    def _select_outcome(self, offer: OfferSpec, action: str) -> OutcomeSpec:
        if action == "approve":
            return offer.approve
        if action == "reject":
            return offer.reject
        if action == "dismiss":
            return offer.dismiss or offer.reject
        raise ActionNotAllowed(f"Unknown action '{action}'")

    def _resolve_outcome_randomness(
        self, outcome: OutcomeSpec
    ) -> tuple[OutcomeSpec, str | None] | None:
        base_resolution = self._resolve_effects_for_manual(
            outcome.effects, self.session.state
        )
        if base_resolution is None:
            return None
        resolved_base, base_state = base_resolution

        resolved_random: list[EffectSpec] = []
        random_label: str | None = None
        if outcome.random:
            choices = self._build_random_choices(outcome.random, base_state)
            choice_index = self._prompt_random_choice(choices)
            if choice_index is None:
                return None
            choice = choices[choice_index]
            random_label = choice["label"]
            random_resolution = self._resolve_effects_for_manual(
                choice["effects"], base_state
            )
            if random_resolution is None:
                return None
            resolved_random, _ = random_resolution

        resolved_outcome = OutcomeSpec(
            effects=tuple(resolved_base + resolved_random),
            random=None,
            notes=outcome.notes,
        )
        return resolved_outcome, random_label

    def _resolve_effects_for_manual(
        self, effects: tuple[EffectSpec, ...], state: GameState
    ) -> tuple[list[EffectSpec], GameState] | None:
        resolved: list[EffectSpec] = []
        current = state
        for effect in effects:
            if effect.type == "random_range_resource":
                if not self._effect_applies(effect, current):
                    continue
                resource = effect.params.get("resource")
                min_value = int(effect.params.get("min", 0))
                max_value = int(effect.params.get("max", 0))
                if max_value < min_value:
                    max_value = min_value
                chosen = min_value
                if max_value != min_value:
                    chosen = self._prompt_random_value(
                        "Random outcome",
                        f"Choose {self._resource_label(resource)} ({min_value}-{max_value})",
                        min_value,
                        max_value,
                    )
                    if chosen is None:
                        return None
                resolved_effect = EffectSpec(
                    type="add_resource",
                    params={"resource": resource, "amount": chosen},
                    when=None,
                    schedule_after_cases=effect.schedule_after_cases,
                    label=effect.label,
                )
                resolved.append(resolved_effect)
                current = apply_effects(current, (resolved_effect,), self.data, None)
                continue
            if effect.type == "random_exchange":
                if not self._effect_applies(effect, current):
                    continue
                take_resource = effect.params.get("take_resource")
                give_resource = effect.params.get("give_resource")
                if not take_resource or not give_resource:
                    continue
                min_value = int(
                    resolve_expr(effect.params.get("min"), current, self.data)
                )
                max_value = int(
                    resolve_expr(effect.params.get("max"), current, self.data)
                )
                if (
                    self.data.defaults.debt_mode == "clamp_to_zero"
                    and take_resource in NON_NEGATIVE_RESOURCES
                ):
                    current_value = int(getattr(current, take_resource))
                    max_value = min(max_value, current_value)
                if max_value < min_value:
                    min_value = max_value
                chosen = min_value
                if max_value != min_value:
                    chosen = self._prompt_random_value(
                        "Random outcome",
                        (
                            f"Choose {self._resource_label(take_resource)} to trade "
                            f"for {self._resource_label(give_resource)} "
                            f"({min_value}-{max_value})"
                        ),
                        min_value,
                        max_value,
                    )
                    if chosen is None:
                        return None
                take_effect = EffectSpec(
                    type="add_resource",
                    params={"resource": take_resource, "amount": -chosen},
                    when=None,
                    schedule_after_cases=effect.schedule_after_cases,
                    label=effect.label,
                )
                give_effect = EffectSpec(
                    type="add_resource",
                    params={"resource": give_resource, "amount": chosen},
                    when=None,
                    schedule_after_cases=effect.schedule_after_cases,
                    label=effect.label,
                )
                resolved.extend([take_effect, give_effect])
                current = apply_effects(
                    current, (take_effect, give_effect), self.data, None
                )
                continue

            resolved.append(effect)
            current = apply_effects(current, (effect,), self.data, None)
        return resolved, current

    def _build_random_choices(
        self, random_spec: BernoulliSpec | CategoricalSpec, state: GameState
    ) -> list[dict[str, object]]:
        choices: list[dict[str, object]] = []
        if isinstance(random_spec, BernoulliSpec):
            for label, effects, key in (
                ("Then", random_spec.then_effects, "then"),
                ("Else", random_spec.else_effects, "else"),
            ):
                summary = summarize_outcome(
                    OutcomeSpec(effects=effects), state, self.data
                )
                resources = self._resources_for_effects(effects)
                choices.append(
                    {
                        "display": f"{label}: {summary}",
                        "effects": effects,
                        "label": key,
                        "summary": summary,
                        "resources": resources,
                    }
                )
        else:
            for idx, choice in enumerate(random_spec.choices, start=1):
                label = choice.label or f"Choice {idx}"
                summary = summarize_outcome(
                    OutcomeSpec(effects=choice.effects), state, self.data
                )
                resources = self._resources_for_effects(choice.effects)
                choices.append(
                    {
                        "display": f"{label}: {summary}",
                        "effects": choice.effects,
                        "label": choice.label,
                        "summary": summary,
                        "resources": resources,
                    }
                )
        return choices

    def _prompt_random_choice(self, choices: list[dict[str, object]]) -> int | None:
        if not choices:
            return None
        dialog = _OutcomeChoiceDialog(
            choices, dark=self._dark_mode, ui_scale=self._ui_scale_factor, parent=self
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        if dialog.selected_index is None:
            return None
        return dialog.selected_index

    def _prompt_random_value(
        self, title: str, label: str, min_value: int, max_value: int
    ) -> int | None:
        dialog = _OutcomeValueDialog(
            title,
            label,
            min_value,
            max_value,
            dark=self._dark_mode,
            ui_scale=self._ui_scale_factor,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_value

    def _effect_applies(self, effect: EffectSpec, state: GameState) -> bool:
        if not effect.when:
            return True
        if isinstance(effect.when, str):
            ctx = expr_util.build_predicate_context(
                case_index=state.case_index,
                coins=state.coins,
                pop=state.pop,
                mh=state.mh,
                dismissals=state.dismissals,
                retirement_chests=state.retirement_chests,
                flags=set(state.flags),
                statuses=set(state.statuses.keys()),
                counters=state.counters,
            )
            return expr_util.evaluate_predicate(effect.when, ctx)
        return True

    def _resource_label(self, resource: object) -> str:
        labels = {
            "coins": "coins",
            "pop": "popularity",
            "mh": "health",
            "dismissals": "dismissals",
            "retirement_chests": "chests",
        }
        return labels.get(str(resource), str(resource))

    def _resources_for_effects(self, effects: tuple[EffectSpec, ...]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for effect in effects:
            for resource in self._resources_from_effect(effect):
                if resource in MAIN_RESOURCES and resource not in seen:
                    seen.add(resource)
                    ordered.append(resource)
        return ordered

    def _resources_from_effect(self, effect: EffectSpec) -> list[str]:
        params = effect.params
        resources: list[str] = []
        if effect.type in {
            "add_resource",
            "set_resource",
            "clamp_resource",
            "multiply_resource",
            "random_range_resource",
            "set_resource_floor",
            "clear_resource_floor",
        }:
            resource = params.get("resource")
            if resource:
                resources.append(str(resource))
        elif effect.type == "random_exchange":
            take_resource = params.get("take_resource")
            give_resource = params.get("give_resource")
            if take_resource:
                resources.append(str(take_resource))
            if give_resource:
                resources.append(str(give_resource))
        elif effect.type == "swap_resources":
            resource_a = params.get("resource_a")
            resource_b = params.get("resource_b")
            if resource_a:
                resources.append(str(resource_a))
            if resource_b:
                resources.append(str(resource_b))
        return resources

    def _apply_best(self) -> None:
        if not self.current_offer:
            self.toast_area.show_toast("Select an offer first.")
            return
        best_action = self._recommended_action()
        if not best_action:
            self.toast_area.show_toast("No recommendation yet.")
            return
        self._apply_action(best_action)

    def _sync_auto_offer(self) -> None:
        if self._sim_mode != "full":
            return
        if self.session.state.ended:
            self._auto_offer_id = None
            self._auto_offer_case = None
            return
        case_index = self.session.state.case_index
        if self._auto_offer_case == case_index and self._auto_offer_id:
            return
        offer_id = select_encounter(
            self.session.state, self.data, self.encounter_model, self.session.rng
        )
        self._auto_offer_id = offer_id
        self._auto_offer_case = case_index

    def _undo(self) -> None:
        self._flush_manual_adjust_log()
        self.session.undo()
        self._refresh()

    def _reset_run(self) -> None:
        self._stop_planner_thread()
        self._manual_adjust_timer.stop()
        self._manual_adjust_pre_state = None
        self.session.reset(reseed=True)
        self.current_offer = None
        self.current_recommendation = None
        self._auto_offer_id = None
        self._auto_offer_case = None
        self.offer_search.clear_selection()
        self._clear_recommendation_ui()
        self._refresh()

    def _update_planner_settings(self) -> None:
        self.planner.config = PlannerConfig(
            horizon_cases=int(self.horizon_spin.value()),
            rollouts_per_action=int(self.rollouts_spin.value()),
            adaptive_rollouts=self.planner.config.adaptive_rollouts,
            adaptive_rollouts_max=self.planner.config.adaptive_rollouts_max,
            risk_preset=self.risk_combo.currentText(),
        )
        self.planner.weights = weights_for_preset(self.planner.config.risk_preset)
        self.planner.reset_cache()
        if self._sim_mode == "none":
            self.current_recommendation = None
            self._clear_recommendation_ui()
            return
        if self.current_offer:
            self.current_recommendation = None
            self.suggestion_panel.best_label.setText("Calculating...")
            self.suggestion_panel.metrics_label.setText("")
            self.suggestion_panel.set_calculating(
                True, self._planner_progress_total(self.current_offer)
            )
            self._start_planner(self.current_offer)

    def _planner_progress_total(self, offer: OfferSpec) -> int | None:
        if self.planner.config.adaptive_rollouts:
            return None
        return len(offer.actions_available) * self.planner.config.rollouts_per_action

    def _reset_planner_progress(self, offer: OfferSpec) -> int | None:
        total = self._planner_progress_total(offer)
        with self._planner_progress_lock:
            self._planner_progress_value = 0
            self._planner_progress_total_value = total
        self._planner_progress_timer.start()
        return total

    def _increment_planner_progress(self, delta: int) -> None:
        with self._planner_progress_lock:
            self._planner_progress_value += delta

    def _tick_planner_progress(self) -> None:
        self._planner_progress_pending = False
        with self._planner_progress_lock:
            total = self._planner_progress_total_value
            value = self._planner_progress_value
        if total is not None and total > 0:
            self.suggestion_panel.update_progress(value)
        self._consume_planner_result()

    def _on_planner_progress_value(self, value: int) -> None:
        self.suggestion_panel.update_progress(value)

    def _stop_planner_progress(self) -> None:
        self._planner_progress_timer.stop()
        with self._planner_progress_lock:
            self._planner_progress_value = 0
            self._planner_progress_total_value = None
        self._planner_progress_pending = False

    def _schedule_progress_tick(self) -> None:
        if self._planner_progress_pending:
            return
        self._planner_progress_pending = True
        self.planner_progress_signal.emit()

    def _consume_planner_result(self) -> None:
        with self._planner_result_lock:
            generation = self._planner_result_generation
            recommendation = self._planner_result
            error = self._planner_result_error
            cancelled = self._planner_result_cancelled
            self._planner_result_generation = None
            self._planner_result = None
            self._planner_result_error = None
            self._planner_result_cancelled = False
        if generation is None or generation != self._planner_generation:
            return
        if cancelled:
            self._stop_planner_progress()
            self._update_action_controls()
            return
        if error:
            self.current_recommendation = None
            self._clear_recommendation_ui()
            self.suggestion_panel.metrics_label.setText("Planner failed.")
            self.toast_area.show_toast(f"Planner failed: {error}")
            self._stop_planner_progress()
            self._update_action_controls()
            return
        if recommendation:
            self.current_recommendation = recommendation
            self.suggestion_panel.update_recommendation(recommendation)
            self._stop_planner_progress()
            self._update_action_controls()

    def _update_action_controls(self) -> None:
        game_over = self._is_game_over()
        for button in (
            self.approve_button,
            self.reject_button,
            self.dismiss_button,
            self.skip_button,
            self.best_button,
        ):
            button.setVisible(not game_over)
        self.game_over_label.setVisible(game_over)
        if not self.current_offer:
            self._set_button_dimmed(self.approve_button, True)
            self._set_button_dimmed(self.reject_button, True)
            self._set_button_dimmed(self.dismiss_button, True)
            self._set_button_dimmed(self.skip_button, False)
            self._set_button_dimmed(self.best_button, True)
            return
        preview_state = self._preview_state_for_offer()
        self._set_button_dimmed(
            self.approve_button,
            self._action_unaffordable("approve", preview_state)
            or self._action_blocked_by_status("approve", preview_state),
        )
        self._set_button_dimmed(
            self.reject_button,
            self._action_unaffordable("reject", preview_state)
            or self._action_blocked_by_status("reject", preview_state),
        )
        self._set_button_dimmed(
            self.dismiss_button,
            self._action_unaffordable("dismiss", preview_state)
            or self._action_blocked_by_status("dismiss", preview_state),
        )
        self._set_button_dimmed(self.skip_button, False)
        best_action = self._recommended_action()
        if best_action and not self.suggestion_panel.is_calculating():
            self._set_button_dimmed(
                self.best_button,
                self._action_unaffordable(best_action, preview_state)
                or self._action_blocked_by_status(best_action, preview_state),
            )
        else:
            self._set_button_dimmed(self.best_button, True)

    def _adjust_resource(self, resource: str, delta: int) -> None:
        if self._manual_adjust_pre_state is None:
            self._manual_adjust_pre_state = self.session.state
        state = self.session.state
        ended = False
        end_reason = None
        if resource == "case_index":
            new_value = max(1, state.case_index + delta)
            self.session.state = replace(
                state, case_index=new_value, ended=ended, end_reason=end_reason
            )
        elif resource == "coins":
            self.session.state = replace(
                state,
                coins=max(0.0, state.coins + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "pop":
            self.session.state = replace(
                state,
                pop=max(0.0, state.pop + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "mh":
            self.session.state = replace(
                state,
                mh=max(0.0, state.mh + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "dismissals":
            self.session.state = replace(
                state,
                dismissals=max(0.0, state.dismissals + delta),
                ended=ended,
                end_reason=end_reason,
            )
        elif resource == "retirement_chests":
            self.session.state = replace(
                state,
                retirement_chests=max(0.0, state.retirement_chests + delta),
                ended=ended,
                end_reason=end_reason,
            )
        else:
            return
        self.current_recommendation = None
        if self.current_offer and self._sim_mode != "none":
            self.suggestion_panel.best_label.setText("Calculating...")
            self.suggestion_panel.metrics_label.setText("")
            self.suggestion_panel.set_calculating(
                True, self._planner_progress_total(self.current_offer)
            )
            self._start_planner(self.current_offer)
        else:
            self._clear_recommendation_ui()
        self._manual_adjust_timer.start()
        self._refresh()

    def _flush_manual_adjust_log(self) -> None:
        if self._manual_adjust_pre_state is None:
            return
        if self._manual_adjust_timer.isActive():
            self._manual_adjust_timer.stop()
        self._commit_manual_adjust_log()

    def _commit_manual_adjust_log(self) -> None:
        pre_state = self._manual_adjust_pre_state
        if pre_state is None:
            return
        self._manual_adjust_pre_state = None
        self.session.log.record_manual_adjust(
            pre_state, self.session.state, self.session.rng.state()
        )
        self._refresh()

    def _action_unaffordable(self, action: str, state: GameState | None = None) -> bool:
        if not self.current_offer:
            return False
        if action not in self.current_offer.actions_available:
            return False
        current_state = state or self.session.state
        return not can_afford_action(
            current_state, self.current_offer, action, self.data
        )

    def _action_blocked_by_status(
        self, action: str, state: GameState | None = None
    ) -> bool:
        if not self.current_offer:
            return False
        if action not in self.current_offer.actions_available:
            return False
        current_state = state or self.session.state
        return is_action_blocked(current_state, self.current_offer, action, self.data)

    def _preview_state_for_offer(self) -> GameState:
        if not self.current_offer:
            return self.session.state
        rng_preview = Rng.from_state(self.session.rng.state())
        return preview_state_after_encounter_triggers(
            self.session.state, self.current_offer, self.data, rng_preview
        )

    def _set_button_dimmed(self, button: QtWidgets.QPushButton, dimmed: bool) -> None:
        if dimmed:
            button.setStyleSheet("color: #8a8a8a;")
        else:
            button.setStyleSheet("")

    def _clear_recommendation_ui(self) -> None:
        self.suggestion_panel.clear_recommendation()

    def _recommended_action(self) -> str | None:
        if self.current_recommendation:
            return self.current_recommendation.best_action
        if self.suggestion_panel.is_calculating():
            return None
        return self.suggestion_panel.last_action

    def _is_game_over(self) -> bool:
        if self.session.state.mh <= 0:
            return True
        if not self.current_offer:
            return False
        actions = list(self.current_offer.actions_available)
        if not actions:
            return True
        return not any(self._action_survives(action) for action in actions)

    def _action_survives(self, action: str) -> bool:
        try:
            preview_state, _ = apply_action(
                self.session.state, self.current_offer, action, self.data, Rng(0)
            )
        except ActionNotAllowed:
            return False
        return preview_state.mh > 0

    def _export_run(self) -> None:
        path_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Run", str(Path.cwd())
        )
        if not path_str:
            return
        run_state = RunState(
            version="run_state_v1",
            state=self.session.state,
            rng_state=self.session.rng.state(),
            log=self.session.log.to_list(),
        )
        save_run_state(Path(path_str), run_state)

    def _import_run(self) -> None:
        path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Run", str(Path.cwd())
        )
        if not path_str:
            return
        run_state = load_run_state(Path(path_str))
        self.session.state = run_state.state
        self.session.rng = Rng.from_state(run_state.rng_state)
        self.session.log = SessionLog.from_list(run_state.log)
        self.current_recommendation = None
        self._refresh()
