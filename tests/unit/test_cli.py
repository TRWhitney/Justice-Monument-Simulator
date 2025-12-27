import pytest
from rich.console import Console

from justice_sim.models.state import GameState
from justice_sim.planner.rollout import ActionScore, PlannerRecommendation
from justice_sim.ui_cli import cli as cli_module
from justice_sim.ui_cli import render as cli_render
from justice_sim.ui_cli import screens as cli_screens
from justice_sim.ui_cli import search as cli_search
from justice_sim.util.search import search_offers
from justice_sim.models.suggested_rules import SuggestedRules


@pytest.mark.unit
def test_cli_render_helpers(data_factory):
    data = data_factory()
    console = Console(record=True)
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    cli_render.render_state(console, state)

    results = search_offers("offer", data, state)
    cli_render.render_search_results(console, results)

    recommendation = PlannerRecommendation(
        best_action="approve",
        action_scores=(
            ActionScore(
                action="approve",
                expected_utility=1.0,
                expected_chests=1.0,
                death_probability=0.0,
                variance=0.0,
            ),
        ),
    )
    cli_render.render_recommendation(console, recommendation)


@pytest.mark.unit
def test_cli_search_wrapper(data_factory):
    data = data_factory()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    results = cli_search.search("offer", data, state)
    assert results


@pytest.mark.unit
def test_cli_screens_wrappers():
    console = Console(record=True)
    state = GameState(
        case_index=1, coins=0, pop=0, mh=3, dismissals=0, retirement_chests=0
    )
    recommendation = PlannerRecommendation(
        best_action="approve",
        action_scores=(
            ActionScore(
                action="approve",
                expected_utility=1.0,
                expected_chests=1.0,
                death_probability=0.0,
                variance=0.0,
            ),
        ),
    )
    cli_screens.show_state(console, state)
    cli_screens.show_recommendation(console, recommendation)


@pytest.mark.unit
def test_run_session_apply_and_undo(data_factory):
    data = data_factory()
    session = cli_module.RunSession(data)
    assert session.state.coins == 5
    assert session.state.pop == 3
    assert session.state.mh == 1
    assert session.state.dismissals == 0
    offer = data.offers_by_id["offer1"]
    session.apply(offer, "approve")
    assert session.state.case_index == 2
    assert len(session.log.entries) == 1
    session.undo()
    assert len(session.log.entries) == 0


@pytest.mark.unit
def test_cli_main_quits_immediately(monkeypatch, data_factory):
    monkeypatch.setattr(cli_module, "prompt", lambda _: "quit")
    monkeypatch.setattr(cli_module, "load_builtin_data", lambda: data_factory())
    monkeypatch.setattr(
        cli_module, "load_builtin_suggested_rules", lambda _data: SuggestedRules.empty()
    )
    assert cli_module.main() == 0


@pytest.mark.unit
def test_cli_main_handles_keyboard_interrupt(monkeypatch, data_factory):
    def _raise_interrupt(_prompt: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "prompt", _raise_interrupt)
    monkeypatch.setattr(cli_module, "load_builtin_data", lambda: data_factory())
    monkeypatch.setattr(
        cli_module, "load_builtin_suggested_rules", lambda _data: SuggestedRules.empty()
    )
    assert cli_module.main() == 0
