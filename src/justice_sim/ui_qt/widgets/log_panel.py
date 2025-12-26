"""Log panel widget."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from justice_sim.persistence.logs import SessionLog


class LogPanel(QtWidgets.QWidget):
    undo_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        self.log_list = QtWidgets.QListWidget()
        self.undo_button = QtWidgets.QPushButton("Undo")
        layout.addWidget(self.log_list)
        layout.addWidget(self.undo_button)
        self.undo_button.clicked.connect(self.undo_requested.emit)

    def update_log(self, log: SessionLog) -> None:
        self.log_list.clear()
        for entry in log.entries:
            label = f"{entry.offer_id}: {entry.action}"
            self.log_list.addItem(label)
