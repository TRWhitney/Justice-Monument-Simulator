import os

import pytest
from PySide6 import QtWidgets

from justice_sim.models.offer import JusticeData
from justice_sim.models.state import GameState
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
    window.best_button.click()

    assert window.toast_area.toast_count() == initial + 2

    window.close()
    app.quit()
