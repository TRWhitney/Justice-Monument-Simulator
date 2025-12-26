"""State display widget."""

from __future__ import annotations

from PySide6 import QtWidgets

from justice_sim.models.state import GameState


class StatePanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QFormLayout(self)
        self.case_label = QtWidgets.QLabel("-")
        self.coins_label = QtWidgets.QLabel("-")
        self.pop_label = QtWidgets.QLabel("-")
        self.mh_label = QtWidgets.QLabel("-")
        self.dismissals_label = QtWidgets.QLabel("-")
        self.chests_label = QtWidgets.QLabel("-")
        layout.addRow("Case", self.case_label)
        layout.addRow("Coins", self.coins_label)
        layout.addRow("Pop", self.pop_label)
        layout.addRow("Health", self.mh_label)
        layout.addRow("Dismissals", self.dismissals_label)
        layout.addRow("Chests", self.chests_label)

    def update_state(self, state: GameState) -> None:
        self.case_label.setText(str(state.case_index))
        self.coins_label.setText(f"{state.coins:g}")
        self.pop_label.setText(f"{state.pop:g}")
        self.mh_label.setText(f"{state.mh:g}")
        self.dismissals_label.setText(f"{state.dismissals:g}")
        self.chests_label.setText(f"{state.retirement_chests:g}")
