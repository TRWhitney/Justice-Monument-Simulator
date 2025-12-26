import os

import pytest
from PySide6 import QtWidgets

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
def test_state_panel_omits_case_and_chest_buttons():
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
        is None
    )
    assert (
        panel.findChild(QtWidgets.QPushButton, "resource_retirement_chests_decrease")
        is None
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
