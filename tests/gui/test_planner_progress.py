import os
import time

import pytest
from PySide6 import QtWidgets

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
