"""Recommendation display panel."""

from __future__ import annotations

from PySide6 import QtWidgets

from justice_sim.planner.rollout import PlannerRecommendation


class SuggestionPanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.best_label = QtWidgets.QLabel("No recommendation")
        self.metrics_label = QtWidgets.QLabel("")
        layout.addWidget(self.best_label)
        layout.addWidget(self.metrics_label)

    def update_recommendation(self, recommendation: PlannerRecommendation) -> None:
        best = max(recommendation.action_scores, key=lambda s: s.expected_utility)
        self.best_label.setText(f"Best: {best.action}")
        self.metrics_label.setText(
            f"Utility {best.expected_utility:.2f} | Chests {best.expected_chests:.2f} | Death {best.death_probability:.2f}"
        )
