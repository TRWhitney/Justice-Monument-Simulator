import os
from dataclasses import replace

import pytest
from PySide6 import QtCore, QtWidgets

from justice_sim.engine.rng import RngState
from justice_sim.models.state import GameState
from justice_sim.persistence.logs import SessionLog
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.widgets.log_panel import LogPanel
from justice_sim.ui_qt.widgets.resource_delta import format_resource_delta_html


@pytest.mark.gui
def test_log_panel_shows_delta_and_popover(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    panel = LogPanel(data)

    pre_state = GameState(
        case_index=1,
        coins=0,
        pop=0,
        mh=3,
        dismissals=0,
        retirement_chests=0,
    )
    post_state = replace(pre_state, coins=2)
    log = SessionLog()
    log.record(pre_state, "offer1", "approve", RngState(seed=0, draws=0), post_state)

    panel.update_log(log)
    panel.show()
    app.processEvents()

    item = panel.log_list.item(0)
    widget = panel.log_list.itemWidget(item)
    assert widget is not None
    label = widget.findChild(QtWidgets.QLabel)
    assert label is not None
    assert label.text() == format_resource_delta_html(pre_state, post_state)

    panel.log_list.itemEntered.emit(item)
    app.processEvents()
    assert panel._popover.isVisible()

    leave_event = QtCore.QEvent(QtCore.QEvent.Type.Leave)
    QtCore.QCoreApplication.sendEvent(panel.log_list.viewport(), leave_event)
    app.processEvents()
    assert not panel._popover.isVisible()

    panel.close()
    app.quit()
