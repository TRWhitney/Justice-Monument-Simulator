"""Main window for the Qt GUI."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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
from justice_sim.models.state import GameState
from justice_sim.persistence.logs import SessionLog
from justice_sim.persistence.runs import RunState, load_run_state, save_run_state
from justice_sim.planner.rollout import (
    PlannerConfig,
    PlannerRecommendation,
    RolloutPlanner,
)
from justice_sim.ui_qt.widgets.log_panel import LogPanel
from justice_sim.ui_qt.widgets.offer_search import OfferSearchWidget
from justice_sim.ui_qt.widgets.state_panel import StatePanel
from justice_sim.ui_qt.widgets.suggestion_panel import SuggestionPanel
from justice_sim.ui_qt.widgets.toast_area import ToastArea
from justice_sim.ui_qt.widgets.resource_delta import format_resource_delta_html
from justice_sim.util import expr as expr_util
from justice_sim.util.render import summarize_outcome


class TitleBar(QtWidgets.QWidget):
    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("title_bar")
        self._drag_pos: QtCore.QPoint | None = None
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

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

        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.min_button)
        layout.addWidget(self.max_button)
        layout.addWidget(self.close_button)

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
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._choices = choices
        self._selected_index: int | None = None
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)

        panel = QtWidgets.QFrame()
        panel.setObjectName("outcome_dialog_panel")
        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(12)
        root_layout.addWidget(panel)

        self._shadow = QtWidgets.QGraphicsDropShadowEffect(panel)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 5)
        panel.setGraphicsEffect(self._shadow)

        title = QtWidgets.QLabel("Choose what happened")
        title.setStyleSheet("font-weight: 700; font-size: 14px;")
        panel_layout.addWidget(title)

        self._combo = QtWidgets.QComboBox()
        self._combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        max_icons = max(
            (len(choice.get("resources", [])) for choice in choices), default=1
        )
        icon_width = _RESOURCE_ICON_SIZE * max_icons + _RESOURCE_ICON_SPACING * (
            max_icons - 1
        )
        self._combo.setIconSize(QtCore.QSize(icon_width, _RESOURCE_ICON_SIZE))
        for choice in choices:
            summary = str(choice.get("display") or choice.get("summary") or "")
            resources = list(choice.get("resources", []))
            icon = self._build_resource_icon(resources, icon_width)
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
        panel.setStyleSheet(
            "QFrame#outcome_dialog_panel {"
            " background-color: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            " stop:0 %(panel_top)s, stop:1 %(panel_bottom)s);"
            " border-radius: 12px;"
            " color: %(fg)s;"
            "}"
            "QComboBox {"
            " background-color: %(field_bg)s;"
            " border: 1px solid %(border)s;"
            " border-radius: 6px;"
            " padding: 4px 8px;"
            "}"
            "QComboBox::drop-down { border: none; }"
            "QPushButton {"
            " background-color: %(btn_bg)s;"
            " border: 1px solid %(border)s;"
            " border-radius: 6px;"
            " padding: 4px 10px;"
            "}"
            "QPushButton:hover { background-color: %(btn_hover)s; }"
            "QPushButton:pressed { background-color: %(btn_pressed)s; }" % palette
        )

    def _build_resource_icon(self, resources: list[str], width: int) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(width, _RESOURCE_ICON_SIZE)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        x = 0
        for resource in resources:
            path = _resolve_resource_icon_path(resource)
            if not path:
                continue
            icon_pix = QtGui.QPixmap(str(path)).scaled(
                _RESOURCE_ICON_SIZE,
                _RESOURCE_ICON_SIZE,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(x, 0, icon_pix)
            x += _RESOURCE_ICON_SIZE + _RESOURCE_ICON_SPACING
        painter.end()
        return QtGui.QIcon(pixmap)

    def _accept_choice(self) -> None:
        self._selected_index = self._combo.currentIndex()
        self.accept()


class PlannerWorker(QtCore.QObject):
    finished = QtCore.Signal(object, int)

    def __init__(
        self,
        planner: RolloutPlanner,
        state: GameState,
        offer: OfferSpec,
        generation: int,
    ) -> None:
        super().__init__()
        self.planner = planner
        self.state = state
        self.offer = offer
        self.generation = generation

    @QtCore.Slot()
    def run(self) -> None:
        recommendation = self.planner.recommend(self.state, self.offer)
        self.finished.emit(recommendation, self.generation)


class GuiSession:
    def __init__(self, data: JusticeData) -> None:
        self.data = data
        self.state = GameState(
            case_index=1,
            coins=5,
            pop=3,
            mh=1,
            dismissals=0,
            retirement_chests=0,
        )
        self.rng = Rng()
        self.log = SessionLog()

    def apply(self, offer: OfferSpec, action: str) -> None:
        pre_state = self.state
        new_state, random_label = apply_action(
            self.state, offer, action, self.data, self.rng
        )
        self.log.record(
            pre_state, offer.id, action, self.rng.state(), new_state, random_label
        )
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
    def __init__(self, data: JusticeData) -> None:
        super().__init__()
        self.data = data
        self.session = GuiSession(data)
        self.planner = RolloutPlanner.from_defaults(data)
        self.encounter_model = UniformEncounterModel()
        self.current_offer: OfferSpec | None = None
        self.current_recommendation: PlannerRecommendation | None = None
        self._planner_generation = 0
        self._planner_thread: QtCore.QThread | None = None
        self._dark_mode = False
        self._auto_offer_id: str | None = None
        self._auto_offer_case: int | None = None

        self.setWindowTitle("Justice Monument Simulator")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
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

        self.full_simulate_checkbox = QtWidgets.QCheckBox("Full simulate")
        self.full_simulate_checkbox.setChecked(False)
        self.full_simulate_checkbox.setToolTip(
            "When enabled, random outcomes are rolled automatically."
        )
        self.full_simulate_checkbox.toggled.connect(self._on_full_simulate_toggled)

        settings_group = QtWidgets.QGroupBox("Planner Settings")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.addRow("Risk", self.risk_combo)
        settings_layout.addRow("Horizon", self.horizon_spin)
        settings_layout.addRow("Rollouts", self.rollouts_spin)
        settings_layout.addRow("Full simulate", self.full_simulate_checkbox)
        left_column.addWidget(settings_group)

        self.import_button = QtWidgets.QPushButton("Import Run")
        self.export_button = QtWidgets.QPushButton("Export Run")
        self.import_button.clicked.connect(self._import_run)
        self.export_button.clicked.connect(self._export_run)
        left_column.addWidget(self.import_button)
        left_column.addWidget(self.export_button)

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
        self.best_button.clicked.connect(self._apply_best)

        right_column.addWidget(self.approve_button)
        right_column.addWidget(self.reject_button)
        right_column.addWidget(self.dismiss_button)
        right_column.addWidget(self.best_button)
        right_column.addWidget(self.game_over_label)

        self.log_panel = LogPanel(data)
        self.log_panel.undo_requested.connect(self._undo)
        right_column.addWidget(self.log_panel)

        self.theme_toggle = QtWidgets.QToolButton(self)
        self.theme_toggle.setCheckable(True)
        self.theme_toggle.setAutoRaise(True)
        self.theme_toggle.setText("☀")
        self.theme_toggle.setToolTip("Light theme")
        self.theme_toggle.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.theme_toggle.toggled.connect(self._on_theme_toggled)
        self._size_grip = QtWidgets.QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)
        self._update_window_controls_geometry()

        self._apply_theme(self._dark_mode)
        self.title_bar.set_maximized(self.isMaximized())
        self._refresh()

    def _refresh(self) -> None:
        self._sync_auto_offer()
        self.state_panel.update_state(self.session.state)
        self.state_panel.set_adjust_enabled(not self.session.log.entries)
        self.log_panel.update_log(self.session.log)
        self.offer_search.set_auto_offer_id(self._auto_offer_id)
        self.offer_search.set_show_all_visible(
            not self.full_simulate_checkbox.isChecked()
        )
        self.offer_search.update_state(self.session.state, preserve_scroll=True)
        self._update_action_controls()
        if self.current_recommendation:
            self.suggestion_panel.update_recommendation(self.current_recommendation)

    def changeEvent(self, event: QtCore.QEvent) -> None:
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

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

    def _on_full_simulate_toggled(self, checked: bool) -> None:
        if not checked:
            self._auto_offer_id = None
            self._auto_offer_case = None
        self._refresh()

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
        self.setStyleSheet(
            "QWidget { background-color: %(bg)s; color: %(fg)s; }"
            "QWidget#root_container { border: 1px solid %(border)s; }"
            "QWidget#title_bar { background-color: %(title_bg)s; border-bottom: 1px solid %(border)s; }"
            "QLabel#title_label { font-weight: 600; padding-left: 4px; }"
            'QToolButton[title_button="true"] { background: transparent; border: none; padding: 2px 6px; }'
            'QToolButton[title_button="true"]:hover { background-color: %(title_hover)s; border-radius: 6px; }'
            'QToolButton[title_button="true"]:pressed { background-color: %(title_pressed)s; border-radius: 6px; }'
            'QToolButton[title_role="close"]:hover { background-color: %(close_hover)s; color: %(close_fg)s; }'
            'QToolButton[title_role="close"]:pressed { background-color: %(close_pressed)s; color: %(close_fg)s; }'
            "QGroupBox { border: 1px solid %(border)s; border-radius: 6px; margin-top: 6px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
            "QLineEdit, QSpinBox, QComboBox, QListWidget {"
            " background-color: %(field_bg)s; border: 1px solid %(border)s; border-radius: 4px; padding: 2px 6px; }"
            "QPushButton {"
            " background-color: %(btn_bg)s; border: 1px solid %(border)s; border-radius: 4px; padding: 4px 8px; }"
            "QPushButton:hover { background-color: %(btn_hover)s; }"
            "QPushButton:pressed { background-color: %(btn_pressed)s; }"
            "QToolButton { background: transparent; border: none; padding: 2px 4px; }"
            "QPushButton:disabled, QToolButton:disabled { color: %(disabled)s; }"
            "QListWidget::item:selected { background-color: %(selected)s; }" % palette
        )
        self.toast_area.set_theme(dark)
        self.log_panel.set_theme(dark)
        self._update_window_controls_geometry()

    def _update_window_controls_geometry(self) -> None:
        size = 44
        margin = 16
        self.theme_toggle.setFixedSize(size, size)
        font = self.theme_toggle.font()
        font.setPointSize(18)
        self.theme_toggle.setFont(font)
        self.theme_toggle.setStyleSheet(
            "QToolButton { border: none; background: transparent; }"
            "QToolButton:hover { background-color: rgba(0, 0, 0, 20); border-radius: 10px; }"
            "QToolButton:pressed { background-color: rgba(0, 0, 0, 40); border-radius: 10px; }"
        )
        geo = self.geometry()
        self.theme_toggle.move(margin, geo.height() - margin - size)
        grip_margin = 10
        self._size_grip.move(
            geo.width() - grip_margin - self._size_grip.width(),
            geo.height() - grip_margin - self._size_grip.height(),
        )

    def _on_offer_selected(self, offer: OfferSpec | None) -> None:
        if offer is None:
            self.current_offer = None
            self.current_recommendation = None
            self._stop_planner_thread()
            self.suggestion_panel.best_label.setText("No recommendation")
            self.suggestion_panel.metrics_label.setText("")
            self._update_action_controls()
            return
        self.current_offer = offer
        self._update_action_controls()
        self._start_planner(offer)

    def _start_planner(self, offer: OfferSpec) -> None:
        self._planner_generation += 1
        generation = self._planner_generation
        self._stop_planner_thread()

        thread = QtCore.QThread()
        worker = PlannerWorker(self.planner, self.session.state, offer, generation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_planner_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._planner_thread = thread
        thread.start()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._stop_planner_thread()
        super().closeEvent(event)

    def _stop_planner_thread(self) -> None:
        if not self._planner_thread:
            return
        self._planner_thread.requestInterruption()
        self._planner_thread.quit()
        self._planner_thread.wait()
        self._planner_thread = None

    def _on_planner_finished(
        self, recommendation: PlannerRecommendation, generation: int
    ) -> None:
        if generation != self._planner_generation:
            return
        self.current_recommendation = recommendation
        self.suggestion_panel.update_recommendation(recommendation)

    def _apply_action(self, action: str) -> None:
        if not self.current_offer:
            self.toast_area.show_toast("Select an offer first.")
            return
        pre_state = self.session.state
        try:
            if self.full_simulate_checkbox.isChecked():
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
            format_resource_delta_html(pre_state, self.session.state)
        )
        self.current_recommendation = None
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
        dialog = _OutcomeChoiceDialog(choices, dark=self._dark_mode, parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        if dialog.selected_index is None:
            return None
        return dialog.selected_index

    def _prompt_random_value(
        self, title: str, label: str, min_value: int, max_value: int
    ) -> int | None:
        value, ok = QtWidgets.QInputDialog.getInt(
            self, title, label, min_value, min_value, max_value
        )
        if not ok:
            return None
        return value

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
        if not self.current_recommendation:
            return
        self._apply_action(self.current_recommendation.best_action)

    def _sync_auto_offer(self) -> None:
        if not self.full_simulate_checkbox.isChecked():
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
        self.session.undo()
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
        if self.current_offer:
            self._start_planner(self.current_offer)

    def _update_action_controls(self) -> None:
        game_over = self._is_game_over()
        for button in (
            self.approve_button,
            self.reject_button,
            self.dismiss_button,
            self.best_button,
        ):
            button.setVisible(not game_over)
        self.game_over_label.setVisible(game_over)
        if not self.current_offer:
            self._set_button_dimmed(self.approve_button, True)
            self._set_button_dimmed(self.reject_button, True)
            self._set_button_dimmed(self.dismiss_button, True)
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
        if self.current_recommendation:
            self._set_button_dimmed(
                self.best_button,
                self._action_unaffordable(
                    self.current_recommendation.best_action, preview_state
                )
                or self._action_blocked_by_status(
                    self.current_recommendation.best_action, preview_state
                ),
            )
        else:
            self._set_button_dimmed(self.best_button, False)

    def _adjust_resource(self, resource: str, delta: int) -> None:
        if self.session.log.entries:
            return
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
        if self.current_offer:
            self._start_planner(self.current_offer)
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
