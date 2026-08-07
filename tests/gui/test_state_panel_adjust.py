import os

import pytest
from PySide6 import QtCore, QtTest, QtWidgets

from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.widgets.state_panel import StatePanel


@pytest.mark.gui
def test_state_panel_emits_adjust_signal():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = StatePanel()
    seen: list[tuple[str, int]] = []
    panel.resource_adjusted.connect(
        lambda resource, delta: seen.append((resource, delta))
    )

    increase = panel.findChild(QtWidgets.QPushButton, "resource_coins_increase")
    assert increase is not None
    increase.click()

    assert seen == [("coins", 1)]

    panel.close()
    app.quit()


@pytest.mark.gui
def test_state_panel_omits_case_buttons():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = StatePanel()

    assert (
        panel.findChild(QtWidgets.QPushButton, "resource_case_index_increase") is None
    )
    assert (
        panel.findChild(QtWidgets.QPushButton, "resource_case_index_decrease") is None
    )
    assert (
        panel.findChild(QtWidgets.QPushButton, "resource_retirement_chests_increase")
        is not None
    )
    assert (
        panel.findChild(QtWidgets.QPushButton, "resource_retirement_chests_decrease")
        is not None
    )

    panel.close()
    app.quit()


@pytest.mark.gui
def test_state_panel_disable_adjustment_buttons():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = StatePanel()
    panel.set_adjust_enabled(False)

    decrease = panel.findChild(QtWidgets.QPushButton, "resource_pop_decrease")
    assert decrease is not None
    assert not decrease.isEnabled()

    panel.close()
    app.quit()


@pytest.mark.gui
def test_state_panel_hold_adjust_accelerates_and_stops_on_release():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = StatePanel()
    panel.show()
    app.processEvents()

    increase = panel.findChild(QtWidgets.QPushButton, "resource_coins_increase")
    assert increase is not None

    timer = QtCore.QElapsedTimer()
    timer.start()
    seen: list[int] = []

    def _on_adjust(resource: str, delta: int) -> None:
        if resource == "coins" and delta == 1:
            seen.append(timer.elapsed())

    panel.resource_adjusted.connect(_on_adjust)

    QtTest.QTest.mousePress(increase, QtCore.Qt.MouseButton.LeftButton)
    QtTest.QTest.qWait(1200)
    QtTest.QTest.mouseRelease(increase, QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()

    assert len(seen) >= 3
    intervals = [seen[index] - seen[index - 1] for index in range(1, len(seen))]
    assert min(intervals[1:]) < intervals[0]

    count_after_release = len(seen)
    QtTest.QTest.qWait(250)
    app.processEvents()
    assert len(seen) == count_after_release

    panel.close()
    app.quit()
