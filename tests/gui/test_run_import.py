import json
import os
from dataclasses import replace

import pytest
from PySide6 import QtWidgets

from justice_sim.engine.rng import Rng
from justice_sim.persistence.runs import RunState, save_run_state
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow


@pytest.mark.gui
@pytest.mark.parametrize("failure", ["history", "json", "missing", "rng"])
def test_failed_import_preserves_complete_session(
    data_factory, tmp_path, monkeypatch, failure
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    window = MainWindow(data_factory())
    try:
        window.skip_button.click()
        state, rng, log = window.session.state, window.session.rng, window.session.log
        path = tmp_path / "run.json"
        save_run_state(
            path,
            RunState("run_state_v1", replace(state, coins=999), Rng(123).state(), [{}]),
        )
        if failure == "json":
            path.write_text("{", encoding="utf-8")
        elif failure == "missing":
            path.unlink()
        elif failure == "rng":
            payload = json.loads(path.read_text())
            payload["rng_state"]["seed"] = "invalid"
            path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(window, "_select_run_file", lambda *args, **kwargs: path)
        toast_count = window.toast_area.toast_count()
        window.import_button.click()
        assert window.session.state is state
        assert window.session.rng is rng
        assert window.session.log is log
        assert (
            window.state_panel.findChild(
                QtWidgets.QLabel, "resource_coins_value"
            ).text()
            == "5"
        )
        assert window.toast_area.toast_count() == toast_count + 1
        assert any(
            "Import failed:" in label.text()
            for label in window.toast_area.findChildren(QtWidgets.QLabel)
        )
    finally:
        window.close()
        app.quit()


@pytest.mark.gui
def test_import_replaces_encounter_and_cancels_pending_adjustment(
    data_factory, tmp_path, monkeypatch
):
    from PySide6 import QtTest
    from justice_sim.models.state import ForcedEncounter

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    window = MainWindow(data_factory())
    try:
        window.planner.config = replace(
            window.planner.config, horizon_cases=1, rollouts_per_action=5
        )
        window.sim_full_radio.setChecked(True)
        old_offer_id = window.current_offer.id
        target = next(
            offer for offer in window.data.offers[:2] if offer.id != old_offer_id
        )
        window.state_panel.findChild(
            QtWidgets.QPushButton, "resource_coins_increase"
        ).click()
        app.processEvents()
        assert window._manual_adjust_timer.isActive()
        imported = replace(
            window.session.state,
            coins=99,
            forced_encounters=(ForcedEncounter(1, target.id),),
        )
        path = tmp_path / "run.json"
        save_run_state(path, RunState("run_state_v1", imported, Rng(123).state(), []))
        monkeypatch.setattr(window, "_select_run_file", lambda *args, **kwargs: path)
        window.import_button.click()
        assert window.current_offer.id == target.id
        assert window.offer_search._selected_offer_id() == target.id
        assert window._auto_offer_id == target.id
        assert window.session.state == imported
        assert window._manual_adjust_pre_state is None
        assert not window._manual_adjust_timer.isActive()
        QtTest.QTest.qWait(450)
        assert window.session.state == imported
        assert not window.session.log.entries
    finally:
        window.close()
        app.quit()
