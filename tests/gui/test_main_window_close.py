import os
import time

import pytest

from PySide6 import QtCore

from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow


class SleepWorker(QtCore.QObject):
    def __init__(self, delay: float = 0.2) -> None:
        super().__init__()
        self.delay = delay

    @QtCore.Slot()
    def run(self) -> None:
        time.sleep(self.delay)


@pytest.mark.gui
def test_main_window_closes_with_active_planner(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    thread = QtCore.QThread()
    worker = SleepWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    assert thread.isRunning()
    window._planner_thread = thread

    window.close()
    app.processEvents()

    assert window._planner_thread is None or not window._planner_thread.isRunning()

    app.quit()
