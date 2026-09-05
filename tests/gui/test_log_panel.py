import os
from dataclasses import replace

import pytest
from PySide6 import QtCore, QtWidgets

from justice_sim.engine.rng import RngState
from justice_sim.models.state import GameState
from justice_sim.persistence.logs import EncounterLuck, SessionLog
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


@pytest.mark.gui
def test_log_panel_popover_shows_luck_ranking(data_factory):
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
    log.record(
        pre_state,
        "offer1",
        "approve",
        RngState(seed=0, draws=0),
        post_state,
        encounter_luck=EncounterLuck(rank=2, total=5),
    )

    panel.update_log(log)
    panel.show()
    app.processEvents()

    item = panel.log_list.item(0)
    panel.log_list.itemEntered.emit(item)
    app.processEvents()

    luck_label = panel._popover.findChild(QtWidgets.QLabel, "encounter_luck_label")
    assert luck_label is not None
    assert "2/5" in luck_label.text()
    assert "color:" in luck_label.text()

    panel.close()
    app.quit()


@pytest.mark.gui
def test_log_refresh_reuses_unchanged_rows_and_updates_edited_tail(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    panel = LogPanel(data_factory())
    log = SessionLog()
    rng = RngState(1, 0)
    state = GameState(1, 5, 3, 1, 0, 0)
    try:
        for case in range(100):
            pre = replace(state, case_index=case + 1)
            log.record(pre, "offer1", "approve", rng, replace(pre, case_index=case + 2))
        panel.resize(350, 500)
        panel.show()
        panel.update_log(log)
        app.processEvents()
        first = panel.log_list.itemWidget(panel.log_list.item(0))
        last = panel.log_list.itemWidget(panel.log_list.item(99))
        scroll = panel.log_list.verticalScrollBar()
        scroll.setValue(scroll.maximum() // 2)
        position = scroll.value()
        panel.update_log(log)
        assert panel.log_list.itemWidget(panel.log_list.item(99)) is last

        log.record_manual_adjust(state, replace(state, coins=6), rng)
        panel.update_log(log)
        assert panel.log_list.count() == 101
        assert panel.log_list.itemWidget(panel.log_list.item(0)) is first
        assert panel.log_list.itemWidget(panel.log_list.item(99)) is last
        assert scroll.value() == position
        log.record_manual_adjust(state, replace(state, coins=8), rng)
        panel.update_log(log)
        edited = panel.log_list.item(100)
        assert edited.data(QtCore.Qt.ItemDataRole.UserRole).post_state.coins == 8
        assert (
            "+3" in panel.log_list.itemWidget(edited).findChild(QtWidgets.QLabel).text()
        )
        log.undo()
        panel.update_log(log)
        assert panel.log_list.count() == 100
        assert panel.log_list.itemWidget(panel.log_list.item(99)) is last
        panel.set_ui_scale(1.3)
        assert panel.log_list.itemWidget(panel.log_list.item(0)) is not first
        panel.update_log(SessionLog())
        assert panel.log_list.count() == 0
    finally:
        panel.close()
        app.quit()
