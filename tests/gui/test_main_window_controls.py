import os
import time
from dataclasses import replace

import pytest
from PySide6 import QtWidgets

from justice_sim.engine.luck import EncounterLuck, encounter_luck_color
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import ActionScore, PlannerRecommendation
from justice_sim.ui_qt.app import create_app
from justice_sim.ui_qt.main_window import MainWindow


@pytest.mark.gui
def test_game_over_label_shown_for_deadly_offer(data_dict_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data_dict = data_dict_factory()
    data_dict["offers"][0]["approve"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
    ]
    data_dict["offers"][0]["reject"]["effects"] = [
        {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
    ]
    data_dict["offers"][0]["actions_available"] = ["approve", "reject"]
    data = JusticeData.from_dict(data_dict)
    window = MainWindow(data)
    window.session.state = GameState(
        case_index=1, coins=0, pop=0, mh=1, dismissals=0, retirement_chests=0
    )
    window.current_offer = data.offers_by_id["offer1"]
    window._update_action_controls()

    assert not window.game_over_label.isHidden()
    assert window.approve_button.isHidden()
    assert window.reject_button.isHidden()
    assert window.dismiss_button.isHidden()
    assert window.skip_button.isHidden()
    assert window.best_button.isHidden()

    window.close()
    app.quit()


@pytest.mark.gui
def test_reject_action_shows_toast(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.current_offer = data.offers_by_id["offer1"]
    window.session.state = GameState(
        case_index=1, coins=0, pop=1, mh=3, dismissals=0, retirement_chests=0
    )

    initial = window.toast_area.toast_count()
    window._apply_action("reject")

    assert window.toast_area.toast_count() == initial + 1

    window.close()
    app.quit()


@pytest.mark.gui
def test_insufficient_funds_toast(data_dict_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data_dict = data_dict_factory()
    data_dict["offers"][0]["approve"]["effects"][0]["params"]["amount"] = -10
    data = JusticeData.from_dict(data_dict)
    window = MainWindow(data)
    window.current_offer = data.offers_by_id["offer1"]

    initial = window.toast_area.toast_count()
    window._apply_action("approve")

    assert window.toast_area.toast_count() == initial + 1

    window.close()
    app.quit()


@pytest.mark.gui
def test_game_over_shown_when_mh_zero(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.session.state = GameState(
        case_index=1, coins=0, pop=1, mh=0, dismissals=0, retirement_chests=0
    )
    window.current_offer = data.offers_by_id["offer1"]
    window._update_action_controls()

    assert not window.game_over_label.isHidden()

    window.close()
    app.quit()


@pytest.mark.gui
def test_game_over_offer_selection_skips_planner(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.session.state = GameState(
        case_index=1, coins=0, pop=1, mh=0, dismissals=0, retirement_chests=0
    )

    class _NoCallPlanner:
        def __init__(self, config):
            self.config = config

        def recommend(self, *_args, **_kwargs):
            raise AssertionError("Planner should not run for game-over state")

    window.planner = _NoCallPlanner(window.planner.config)
    window._on_offer_selected(data.offers_by_id["offer1"])

    assert not window.suggestion_panel.is_calculating()
    assert window.suggestion_panel.best_label.text() == "No recommendation"

    window.close()
    app.quit()


@pytest.mark.gui
def test_dismiss_button_dimmed_without_dismissals(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.session.state = GameState(
        case_index=1, coins=0, pop=1, mh=2, dismissals=0, retirement_chests=0
    )
    window.current_offer = data.offers_by_id["offer1"]
    window._update_action_controls()

    assert window.dismiss_button.isEnabled()
    assert window.dismiss_button.styleSheet() == "color: #8a8a8a;"

    window.close()
    app.quit()


@pytest.mark.gui
def test_game_over_when_no_valid_actions(data_dict_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data_dict = data_dict_factory()
    data_dict["offers"][0]["approve"]["effects"][0]["params"]["amount"] = -1
    data_dict["offers"][0]["reject"]["effects"][0]["params"]["amount"] = -1
    data_dict["offers"][0]["reject"]["effects"][0]["params"]["resource"] = "coins"
    data = JusticeData.from_dict(data_dict)
    window = MainWindow(data)
    window.session.state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    window.current_offer = data.offers_by_id["offer1"]
    window._update_action_controls()

    assert not window.game_over_label.isHidden()

    window.close()
    app.quit()


@pytest.mark.gui
def test_state_panel_adjust_updates_state(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)

    assert window.session.state.coins == 5
    assert window.session.state.pop == 3
    assert window.session.state.mh == 1
    assert window.session.state.dismissals == 0

    increase = window.state_panel.findChild(
        QtWidgets.QPushButton, "resource_coins_increase"
    )
    assert increase is not None
    increase.click()
    assert window.session.state.coins == 6

    window.close()
    app.quit()


@pytest.mark.gui
def test_reset_run_button_resets_state_and_rng(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.show()
    QtWidgets.QApplication.processEvents()

    window.session.state = replace(
        window.session.state,
        case_index=5,
        coins=0,
        pop=0,
        mh=2,
        dismissals=1,
        retirement_chests=1,
    )
    window.session.rng = Rng(1234)
    offer = data.offers_by_id["offer1"]
    window.session.log.record(
        window.session.state,
        offer.id,
        "approve",
        window.session.rng.state(),
        window.session.state,
    )
    assert window.session.log.entries

    reset = window.findChild(QtWidgets.QPushButton, "reset_run_button")
    assert reset is not None
    reset.click()
    QtWidgets.QApplication.processEvents()

    state = window.session.state
    assert state.case_index == 1
    assert state.coins == 5
    assert state.pop == 3
    assert state.mh == 1
    assert state.dismissals == 0
    assert state.retirement_chests == 0
    assert window.session.rng.seed != 1234
    assert not window.session.log.entries

    window.close()
    app.quit()


@pytest.mark.gui
def test_action_buttons_dimmed_without_offer(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.current_offer = None
    window._update_action_controls()

    assert window.approve_button.styleSheet() == "color: #8a8a8a;"
    assert window.reject_button.styleSheet() == "color: #8a8a8a;"
    assert window.dismiss_button.styleSheet() == "color: #8a8a8a;"
    assert window.skip_button.styleSheet() == ""
    assert window.best_button.styleSheet() == "color: #8a8a8a;"

    window.close()
    app.quit()


@pytest.mark.gui
def test_action_buttons_toast_without_offer(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.current_offer = None

    initial = window.toast_area.toast_count()
    window.approve_button.click()
    window.skip_button.click()
    window.best_button.click()

    assert window.toast_area.toast_count() == initial + 3

    window.close()
    app.quit()


@pytest.mark.gui
def test_resource_adjust_debounces_planner_and_log_refresh(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)
    window.current_offer = data.offers_by_id["offer1"]
    window._manual_adjust_timer.setInterval(80)

    class _CountingPlanner:
        def __init__(self, config) -> None:
            self.config = config
            self.calls = 0

        def recommend(self, _state, offer, progress=None):
            self.calls += 1
            scores = tuple(
                ActionScore(
                    action=action,
                    expected_utility=1.0,
                    expected_chests=0.0,
                    death_probability=0.0,
                    variance=0.0,
                )
                for action in offer.actions_available
            )
            return PlannerRecommendation(
                best_action=offer.actions_available[0], action_scores=scores
            )

    planner = _CountingPlanner(window.planner.config)
    window.planner = planner
    window._on_offer_selected(data.offers_by_id["offer1"])
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and planner.calls < 1:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    baseline_calls = planner.calls

    window._adjust_resource("coins", 1)
    window._adjust_resource("coins", 1)
    QtWidgets.QApplication.processEvents()

    assert window.session.state.coins == 7
    assert planner.calls == baseline_calls
    assert not window.session.log.entries

    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and planner.calls < baseline_calls + 1:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)

    assert planner.calls == baseline_calls + 1
    assert window.session.log.entries
    assert window.session.log.entries[-1].action == "adjust"

    window.close()
    app.quit()


@pytest.mark.gui
def test_run_luck_indicator_aggregates_logged_deal_luck(data_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    data = data_factory()
    window = MainWindow(data)

    assert "n/a" in window.run_luck_label.text().lower()

    offer = data.offers_by_id["offer1"]
    pre_one = GameState(
        case_index=1, coins=5, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    post_one = replace(pre_one, case_index=2)
    pre_two = post_one
    post_two = replace(pre_two, case_index=3)

    window.session.log.record(
        pre_one,
        offer.id,
        "approve",
        window.session.rng.state(),
        post_one,
        encounter_luck=EncounterLuck(rank=1, total=5),
    )
    window.session.log.record(
        pre_two,
        offer.id,
        "reject",
        window.session.rng.state(),
        post_two,
        encounter_luck=EncounterLuck(rank=5, total=5),
    )

    window._refresh()
    expected_color = encounter_luck_color(51, 100)
    text = window.run_luck_label.text()
    assert "50%" in text
    assert "(2 deals)" in text
    assert expected_color in text

    window.close()
    app.quit()
