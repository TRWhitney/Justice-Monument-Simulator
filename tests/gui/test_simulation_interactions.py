"""Direct Qt interaction checks for the simulation audit fixes."""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6 import QtCore, QtWidgets

from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerConfig
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow

pytestmark = pytest.mark.gui


@pytest.fixture
def audit_window(builtin_data, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    original_font = app.font()
    # Keep the real affected offers and complete Harbinger pool. Rendering every
    # unrelated card here duplicates the existing search/layout test coverage.
    prefixes = (
        "scripticus_hey_it_s",
        "cool_bird_sup_heads_you_the_man",
        "ghost_can_you",
        "rupie_slug_hai_you",
        "billionaire_chester_",
    )
    special_ids = {
        *builtin_data.special_rules.harbinger.offer_pool,
        builtin_data.special_rules.harbinger.offer_id,
        builtin_data.special_rules.gratefulbinger.offer_id,
    }
    offers = tuple(
        offer
        for offer in builtin_data.offers
        if offer.id.startswith(prefixes) or offer.id in special_ids
    )
    data = replace(builtin_data, offers=offers, offers_by_id={o.id: o for o in offers})
    window = MainWindow(data, theme_override=False, ui_scale_override="medium")
    window._tour_seen = True
    window._sim_mode = "none"
    window.planner.config = PlannerConfig(
        horizon_cases=0, rollouts_per_action=8, adaptive_rollouts=False
    )
    window.show()
    QtWidgets.QApplication.processEvents()
    yield window
    window.close()
    window.deleteLater()
    QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    QtWidgets.QApplication.processEvents()
    app.setFont(original_font)


def _capture_review(widget, name):
    # Explicit opt-in artifact workflow; ordinary verification writes no images.
    destination = os.environ.get("JUSTICE_AUDIT_ARTIFACT_DIR")
    if destination:
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        assert widget.grab().save(str(directory / f"{name}.png"))


def test_rounded_harbinger_payment_is_clickable(audit_window):
    window = audit_window
    offer = next(o for o in window.data.offers if "shark_attack" in o.id)
    window.session.state = GameState(15, 11, 3, 1, 0, 0)
    window.current_offer = offer
    window._update_action_controls()
    assert window.game_over_label.isHidden()
    assert not window.approve_button.isHidden()
    assert window.approve_button.styleSheet() == ""
    _capture_review(window, "rounded-harbinger-payment")
    window.approve_button.click()
    assert window.session.state.coins == 0
    assert window.session.state.mh == 1
    assert window.session.state.case_index == 16
