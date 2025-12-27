import os
import threading
import time

import pytest

from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow


def _sleep_worker(delay: float = 0.2) -> None:
    time.sleep(delay)


@pytest.mark.gui
def test_main_window_closes_with_active_planner(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    thread = threading.Thread(target=_sleep_worker, daemon=True)
    thread.start()
    assert thread.is_alive()
    window._planner_thread = thread

    window.close()
    app.processEvents()

    assert window._planner_thread is None or not window._planner_thread.is_alive()

    app.quit()
