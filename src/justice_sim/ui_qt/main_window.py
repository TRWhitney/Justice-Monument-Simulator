"""Main window for the Qt GUI."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from justice_sim.engine.encounter import UniformEncounterModel
from justice_sim.engine.reducer import ActionNotAllowed, apply_action, can_afford_action
from justice_sim.engine.rng import Rng
from justice_sim.engine.scoring import weights_for_preset
from justice_sim.models.offer import JusticeData, OfferSpec
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

        self.setWindowTitle("Justice Monument Simulator")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

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

        settings_group = QtWidgets.QGroupBox("Planner Settings")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.addRow("Risk", self.risk_combo)
        settings_layout.addRow("Horizon", self.horizon_spin)
        settings_layout.addRow("Rollouts", self.rollouts_spin)
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

        self._refresh()

    def _refresh(self) -> None:
        self.state_panel.update_state(self.session.state)
        self.state_panel.set_adjust_enabled(not self.session.log.entries)
        self.log_panel.update_log(self.session.log)
        self.offer_search.update_state(self.session.state, preserve_scroll=True)
        self._update_action_controls()
        if self.current_recommendation:
            self.suggestion_panel.update_recommendation(self.current_recommendation)

    def _on_offer_selected(self, offer: OfferSpec) -> None:
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
            self.session.apply(self.current_offer, action)
        except ActionNotAllowed as exc:
            self.toast_area.show_toast(f"{action.title()} failed: {exc}")
            return
        self.toast_area.show_toast(
            format_resource_delta_html(pre_state, self.session.state)
        )
        self.current_recommendation = None
        self._refresh()

    def _apply_best(self) -> None:
        if not self.current_offer:
            self.toast_area.show_toast("Select an offer first.")
            return
        if not self.current_recommendation:
            return
        self._apply_action(self.current_recommendation.best_action)

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
        self._set_button_dimmed(
            self.approve_button, self._action_unaffordable("approve")
        )
        self._set_button_dimmed(self.reject_button, self._action_unaffordable("reject"))
        self._set_button_dimmed(
            self.dismiss_button, self._action_unaffordable("dismiss")
        )
        if self.current_recommendation:
            self._set_button_dimmed(
                self.best_button,
                self._action_unaffordable(self.current_recommendation.best_action),
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

    def _action_unaffordable(self, action: str) -> bool:
        if not self.current_offer:
            return False
        if action not in self.current_offer.actions_available:
            return False
        return not can_afford_action(
            self.session.state, self.current_offer, action, self.data
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
