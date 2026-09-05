"""Real Mid-mode selection, worker completion, and recommendation reuse."""

import os
from dataclasses import replace
from pathlib import Path
import time

import pytest
from PySide6 import QtCore, QtWidgets

from justice_sim.engine.rng import Rng
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def window(data_factory):
    app = create_app()
    window = MainWindow(
        data_factory(), theme_override=False, ui_scale_override="medium"
    )
    window._tour_seen = True
    window.planner.rng = Rng(42)
    window.horizon_spin.setValue(1)
    window.rollouts_spin.setValue(10)
    window.show()
    app.processEvents()
    yield window
    window.close()
    window.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    app.processEvents()


def _select(window, offer_id):
    window.offer_search.search_input.setText("")
    index = next(
        i
        for i, result in enumerate(window.offer_search._results)
        if result.offer.id == offer_id
    )
    window.offer_search.results_list.setCurrentRow(index)
    QtWidgets.QApplication.processEvents()


def _wait_for_result(window):
    deadline = time.monotonic() + 8
    while window.current_recommendation is None and time.monotonic() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)
    assert window.current_recommendation is not None
    assert window._planner_process is None
    return window.current_recommendation


def _capture(window, name):
    destination = os.environ.get("JUSTICE_OPTIMIZATION_ARTIFACT_DIR")
    if destination:
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        assert window.grab().save(str(directory / f"{name}.png"))


def test_mid_reuses_completed_offer_then_recalculates_changed_state(
    window, monkeypatch
):
    from justice_sim.ui_qt import main_window

    original_context = main_window.multiprocessing.get_context
    starts = []

    def record_context(*args, **kwargs):
        starts.append(True)
        return original_context(*args, **kwargs)

    monkeypatch.setattr(main_window.multiprocessing, "get_context", record_context)
    assert window._sim_mode == "mid"
    _select(window, "offer1")
    first = _wait_for_result(window)
    _select(window, "offer2")
    _wait_for_result(window)
    assert len(starts) == 2
    _select(window, "offer1")
    assert window.current_recommendation is first
    assert len(starts) == 2
    assert not window._planner_progress_timer.isActive()
    _capture(window, "mid-cached-recommendation")

    window._adjust_resource("coins", 1)
    window._finalize_manual_adjust()
    _wait_for_result(window)
    assert len(starts) == 3
    window.risk_combo.setCurrentText("safe")
    _wait_for_result(window)
    assert len(starts) == 4


def test_recommendation_key_tracks_seed_rules_model_and_offer(window):
    from justice_sim.engine.encounter import WeightedEncounterModel
    from justice_sim.models.suggested_rules import SuggestedRules

    offer = window.data.offers_by_id["offer1"]
    state_key = window._luck_state_key(window.session.state)
    first = window._recommendation_cache_key(offer, state_key)
    window.planner.rng = Rng(99)
    assert window._recommendation_cache_key(offer, state_key) != first
    window.planner.rng = Rng(42)
    window.planner.encounter_model = WeightedEncounterModel(offer_weights={"offer1": 2})
    second = window._recommendation_cache_key(offer, state_key)
    assert second != first
    window.planner.encounter_model.offer_weights["offer1"] = 3
    assert window._recommendation_cache_key(offer, state_key) != second
    window.planner.suggested_rules = SuggestedRules.from_dict(
        {"version": "custom", "rules": []}
    )
    assert window._recommendation_cache_key(offer, state_key) != second
    assert window._recommendation_cache_key(
        replace(offer, title="Changed"), state_key
    ) != window._recommendation_cache_key(offer, state_key)
