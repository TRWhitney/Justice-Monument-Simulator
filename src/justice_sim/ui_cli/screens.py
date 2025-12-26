"""CLI screen flow helpers."""

from __future__ import annotations

from rich.console import Console

from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerRecommendation
from justice_sim.ui_cli.render import render_recommendation, render_state


def show_state(console: Console, state: GameState) -> None:
    render_state(console, state)


def show_recommendation(
    console: Console, recommendation: PlannerRecommendation
) -> None:
    render_recommendation(console, recommendation)
