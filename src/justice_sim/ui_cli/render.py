"""Rich rendering helpers for the CLI."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from justice_sim.models.state import GameState
from justice_sim.planner.rollout import PlannerRecommendation
from justice_sim.util.search import OfferSearchResult
from justice_sim.util.render import summarize_offer, summarize_outcome
from justice_sim.models.offer import JusticeData, OfferSpec, OutcomeSpec
from justice_sim.persistence.logs import LogEntry, SessionLog


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
    table.add_column("Text")
    table.add_column("Approve")
    table.add_column("Reject")
    table.add_column("Dismiss")
    for index, result in enumerate(results, start=1):
        text = _truncate(result.offer.text)
        table.add_row(
            str(index),
            result.npc_name,
            result.offer.title,
            text,
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


def render_offer_detail(
    console: Console, data: JusticeData, offer: OfferSpec, state: GameState
) -> None:
    approve_summary, reject_summary, dismiss_summary = summarize_offer(
        offer, state, data
    )
    table = Table(title="Selected Offer")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("NPC", _npc_name(data, offer.npc_id))
    table.add_row("Title", offer.title)
    table.add_row("Text", offer.text)
    table.add_row("Approve", approve_summary)
    table.add_row("Reject", reject_summary)
    table.add_row("Dismiss", dismiss_summary or "-")
    table.add_row("Actions", ", ".join(offer.actions_available))
    console.print(table)


def render_log_entries(console: Console, log: SessionLog, data: JusticeData) -> None:
    table = Table(title="Log")
    table.add_column("#")
    table.add_column("Case")
    table.add_column("NPC")
    table.add_column("Offer")
    table.add_column("Action")
    table.add_column("Delta")
    table.add_column("Random")
    for index, entry in enumerate(log.entries, start=1):
        offer = data.offers_by_id.get(entry.offer_id)
        npc_name = _npc_name(data, offer.npc_id) if offer else entry.offer_id
        offer_title = offer.title if offer else entry.offer_id
        table.add_row(
            str(index),
            str(entry.pre_state.case_index),
            npc_name,
            offer_title,
            entry.action,
            _format_resource_delta(
                entry.pre_state, entry.post_state, action=entry.action
            ),
            entry.random_label or "-",
        )
    console.print(table)


def render_log_entry_detail(
    console: Console, entry: LogEntry, data: JusticeData
) -> None:
    offer = data.offers_by_id.get(entry.offer_id)
    if not offer:
        table = Table(title=f"Log Entry {entry.timestamp}")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Offer", entry.offer_id)
        table.add_row("Action", entry.action)
        if entry.random_label:
            table.add_row("Random", entry.random_label)
        table.add_row(
            "Delta",
            _format_resource_delta(
                entry.pre_state, entry.post_state, action=entry.action
            ),
        )
        table.add_row(
            "Case", f"{entry.pre_state.case_index} → {entry.post_state.case_index}"
        )
        console.print(table)
        return
    table = Table(title=f"Log Entry {entry.timestamp}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("NPC", _npc_name(data, offer.npc_id))
    table.add_row("Offer", offer.title)
    table.add_row("Action", entry.action)
    if entry.random_label:
        table.add_row("Random", entry.random_label)
    table.add_row(
        "Delta",
        _format_resource_delta(entry.pre_state, entry.post_state, action=entry.action),
    )
    table.add_row(
        "Case", f"{entry.pre_state.case_index} → {entry.post_state.case_index}"
    )
    console.print(table)


def render_effect_summary(
    console: Console, title: str, effects: tuple, state: GameState, data: JusticeData
) -> None:
    summary = summarize_outcome(OutcomeSpec(effects=effects), state, data)
    table = Table(title=title)
    table.add_column("Summary")
    table.add_row(summary)
    console.print(table)


def _npc_name(data: JusticeData, npc_id: str) -> str:
    npc = data.npcs_by_id.get(npc_id)
    return npc.name if npc else npc_id


def _format_resource_delta(
    before: GameState, after: GameState, *, action: str | None = None
) -> str:
    deltas = {
        "coins": after.coins - before.coins,
        "pop": after.pop - before.pop,
        "mh": after.mh - before.mh,
        "dismissals": after.dismissals - before.dismissals,
        "retirement_chests": after.retirement_chests - before.retirement_chests,
    }
    parts: list[str] = []
    for resource, delta in deltas.items():
        if abs(delta) <= 1e-9:
            continue
        sign = "+" if delta > 0 else "-"
        parts.append(f"{sign}{abs(delta):g} {resource}")
    if parts:
        return ", ".join(parts)
    if action == "skip":
        return "No effect (skip)"
    return "No effect"


def _truncate(text: str, limit: int = 48) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."
