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
        self.last_action: str | None = None
        self._calculating = False
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        progress_policy = self.progress.sizePolicy()
        progress_policy.setRetainSizeWhenHidden(True)
        self.progress.setSizePolicy(progress_policy)
        self.progress.hide()
        self.progress_label = QtWidgets.QLabel("")
        label_policy = self.progress_label.sizePolicy()
        label_policy.setRetainSizeWhenHidden(True)
        self.progress_label.setSizePolicy(label_policy)
        self.progress_label.hide()
        layout.addWidget(self.best_label)
        layout.addWidget(self.metrics_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.progress_label)

    def update_recommendation(self, recommendation: PlannerRecommendation) -> None:
        best = next(
            score
            for score in recommendation.action_scores
            if score.action == recommendation.best_action
        )
        self.best_label.setText(f"Best: {recommendation.best_action}")
        self.metrics_label.setText(
            f"Utility {best.expected_utility:.2f} | Chests {best.expected_chests:.2f} | Death {best.death_probability:.2f}"
        )
        self.last_action = recommendation.best_action
        self.set_calculating(False)

    def clear_recommendation(self) -> None:
        self.best_label.setText("No recommendation")
        self.metrics_label.setText("")
        self.last_action = None
        self.set_calculating(False)

    def set_calculating(self, calculating: bool, total: int | None = None) -> None:
        self._calculating = calculating
        if calculating:
            self.last_action = None
            if total and total > 0:
                self.progress.setRange(0, total)
                self.progress.setValue(0)
                self.progress_label.setText(f"0 / {total}")
            else:
                self.progress.setRange(0, 0)
                self.progress_label.setText("")
            self.progress.setVisible(True)
            self.progress_label.setVisible(bool(total))
        else:
            self.progress.setVisible(False)
            self.progress_label.setVisible(False)

    def is_calculating(self) -> bool:
        return self._calculating

    def update_progress(self, value: int) -> None:
        if not self.progress.isVisible():
            return
        if self.progress.minimum() == 0 and self.progress.maximum() == 0:
            return
        capped = min(value, self.progress.maximum())
        self.progress.setValue(capped)
        self.progress_label.setText(f"{capped} / {self.progress.maximum()}")
