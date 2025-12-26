"""Rich rendering helpers for the CLI."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerRecommendation
from justice_sim.util.search import OfferSearchResult


def render_state(console: Console, state: GameState) -> None:
    table = Table(title="Current State")
    table.add_column("Case")
    table.add_column("Coins")
    table.add_column("Pop")
    table.add_column("Health")
    table.add_column("Dismissals")
    table.add_column("Chests")
    table.add_row(
        str(state.case_index),
        f"{state.coins:g}",
        f"{state.pop:g}",
        f"{state.mh:g}",
        f"{state.dismissals:g}",
        f"{state.retirement_chests:g}",
    )
    console.print(table)


def render_search_results(console: Console, results: list[OfferSearchResult]) -> None:
    table = Table(title="Offers")
    table.add_column("#")
    table.add_column("NPC")
    table.add_column("Title")
    table.add_column("Approve")
    table.add_column("Reject")
    table.add_column("Dismiss")
    for index, result in enumerate(results, start=1):
        table.add_row(
            str(index),
            result.npc_name,
            result.offer.title,
            result.approve_summary,
            result.reject_summary,
            result.dismiss_summary or "-",
        )
    console.print(table)


def render_recommendation(
    console: Console, recommendation: PlannerRecommendation
) -> None:
    table = Table(title="Recommendation")
    table.add_column("Action")
    table.add_column("Expected Utility")
    table.add_column("Expected Chests")
    table.add_column("Death Prob")
    for score in sorted(
        recommendation.action_scores, key=lambda s: s.expected_utility, reverse=True
    ):
        table.add_row(
            score.action,
            f"{score.expected_utility:.2f}",
            f"{score.expected_chests:.2f}",
            f"{score.death_probability:.2f}",
        )
    console.print(table)
