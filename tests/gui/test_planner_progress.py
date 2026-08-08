import os
import time

import pytest
from PySide6 import QtCore, QtWidgets

from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import (
    ActionScore,
    PlannerConfig,
    PlannerRecommendation,
)
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow


class FakePlanner:
    def __init__(self) -> None:
        self.config = PlannerConfig(
            horizon_cases=1,
            rollouts_per_action=20,
            adaptive_rollouts=False,
            adaptive_rollouts_max=20,
            risk_preset="balanced",
        )

    def recommend(self, state, offer, progress=None):
        total = len(offer.actions_available) * self.config.rollouts_per_action
        for _ in range(total):
            if progress:
                progress(1)
            time.sleep(0.005)
        scores = tuple(
            ActionScore(
                action=action,
                expected_utility=1.0,
                expected_chests=0.0,
                death_probability=0.0,
                variance=0.0,
            )
            for action in offer.actions_available
        )
        return PlannerRecommendation(
            best_action=offer.actions_available[0], action_scores=scores
        )


class CpuBoundPlanner(FakePlanner):
    def recommend(self, state, offer, progress=None):
        deadline = time.monotonic() + 0.6
        accumulator = 1
        while time.monotonic() < deadline:
            accumulator = (accumulator * 3 + 1) % 1_000_003
        assert accumulator >= 0
        return super().recommend(state, offer, progress=progress)


@pytest.mark.gui
def test_full_simulate_toggle_updates_progress(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.planner = FakePlanner()
    window.show()
    QtWidgets.QApplication.processEvents()

    window.sim_full_radio.setChecked(True)
    QtWidgets.QApplication.processEvents()

    assert not window.suggestion_panel.progress.isHidden()
    assert not window.suggestion_panel.progress_label.isHidden()

    total = window.suggestion_panel.progress.maximum()
    assert total > 0

    deadline = time.monotonic() + 2.0
    updated = False
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        text = window.suggestion_panel.progress_label.text()
        if text and not text.startswith("0 /"):
            updated = True
            break
        time.sleep(0.01)

    assert updated

    window.close()
    app.quit()


@pytest.mark.gui
def test_cpu_bound_planner_keeps_qt_event_loop_responsive(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    window = MainWindow(data_factory())
    window.planner = CpuBoundPlanner()
    window.show()
    QtWidgets.QApplication.processEvents()

    ticks: list[float] = []
    timer = QtCore.QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()

    window.sim_full_radio.setChecked(True)
    deadline = time.monotonic() + 0.4
    while time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.001)

    assert len(ticks) >= 10
    assert window._planner_process is not None
    assert window._planner_process.is_alive()

    timer.stop()
    window.close()
    app.quit()


@pytest.mark.gui
def test_planner_process_returns_recommendation(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )

    window._on_offer_selected(data.offers[0])
    deadline = time.monotonic() + 3.0
    while window.current_recommendation is None and time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)

    assert window.current_recommendation is not None
    assert window._planner_process is None
    assert not window.suggestion_panel.is_calculating()

    window.close()
    app.quit()


@pytest.mark.gui
def test_planner_process_recovers_missing_derived_counter_cache(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )
    del window.planner._referenced_counters

    window._on_offer_selected(data.offers[0])
    deadline = time.monotonic() + 3.0
    while window._planner_process is not None and time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)

    assert window.current_recommendation is not None
    assert window.suggestion_panel.best_label.text() != "No recommendation"
    assert window.suggestion_panel.metrics_label.text() != "Planner failed."

    window.close()
    app.quit()


@pytest.mark.gui
def test_recommended_button_uses_affordable_action(data_dict_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data_dict = data_dict_factory()
    offer_dict = data_dict["offers"][0]
    offer_dict["actions_available"] = ["approve", "reject"]
    offer_dict["approve"] = {
        "effects": [
            {
                "type": "add_resource",
                "params": {"resource": "coins", "amount": -10},
            }
        ]
    }
    offer_dict["reject"] = {
        "effects": [
            {
                "type": "add_resource",
                "params": {"resource": "pop", "amount": -1},
            }
        ]
    }
    data = JusticeData.from_dict(data_dict)
    window = MainWindow(data)
    window.session.state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    window.planner.config = PlannerConfig(
        horizon_cases=1,
        rollouts_per_action=5,
        adaptive_rollouts=False,
        adaptive_rollouts_max=5,
        risk_preset="balanced",
    )

    window._on_offer_selected(data.offers_by_id["offer1"])
    deadline = time.monotonic() + 3.0
    while window.current_recommendation is None and time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)

    assert window.current_recommendation is not None
    assert window.current_recommendation.best_action == "reject"
    assert window.suggestion_panel.best_label.text() == "Best: reject"
    assert window.best_button.styleSheet() == ""

    window.best_button.click()

    assert window.session.state.case_index == 2
    assert window.session.state.coins == 0
    assert window.session.state.pop == 0

    window.close()
    app.quit()
