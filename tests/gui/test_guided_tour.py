import os

import pytest
from PySide6 import QtWidgets

from justice_sim.config import load_builtin_data
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow


@pytest.mark.gui
def test_guided_tour_shows_on_startup():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = load_builtin_data()
    window = MainWindow(data)
    window.show()
    QtWidgets.QApplication.processEvents()

    prompt = window.findChild(QtWidgets.QDialog, "guided_tour_prompt")
    assert prompt is not None
    assert prompt.isVisible()

    start = prompt.findChild(QtWidgets.QPushButton, "tour_start_button")
    assert start is not None
    start.click()
    QtWidgets.QApplication.processEvents()

    panel = window.findChild(QtWidgets.QWidget, "guided_tour_panel")
    assert panel is not None
    assert panel.isVisible()
    assert getattr(panel, "title_label", None) is not None
    assert panel.title_label.text()

    window.close()
    app.quit()
