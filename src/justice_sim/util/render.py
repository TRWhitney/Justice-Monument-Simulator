"""Offer summary rendering helpers shared by CLI and GUI."""

from __future__ import annotations

from typing import Iterable

from justice_sim.engine.effects import resolve_expr
from justice_sim.models.offer import EffectSpec, JusticeData, OutcomeSpec
from justice_sim.models.state import GameState


_RESOURCE_LABELS = {
    "coins": "coins",
    "pop": "pop",
    "mh": "health",
    "dismissals": "dismissals",
    "retirement_chests": "chests",
}


def summarize_outcome(outcome: OutcomeSpec, state: GameState, data: JusticeData) -> str:
    parts = []
    parts.extend(_summarize_effects(outcome.effects, state, data))
    if outcome.random:
        parts.append("random outcome")
    return "; ".join(parts) if parts else "No effect"


def summarize_offer(
    offer, state: GameState, data: JusticeData
) -> tuple[str, str, str | None]:
    approve_summary = summarize_outcome(offer.approve, state, data)
    reject_summary = summarize_outcome(offer.reject, state, data)
    dismiss_summary = (
        summarize_outcome(offer.dismiss, state, data) if offer.dismiss else None
    )
    return approve_summary, reject_summary, dismiss_summary


def _summarize_effects(
    effects: Iterable[EffectSpec], state: GameState, data: JusticeData
) -> list[str]:
    parts: list[str] = []
    for effect in effects:
        params = effect.params
        if effect.type == "add_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            parts.append(
                f"{_format_delta(params.get('amount'), state, data)} {resource}"
            )
        elif effect.type == "set_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            value = _format_value(params.get("value"), state, data)
            parts.append(f"set {resource}={value}")
        elif effect.type == "clamp_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            parts.append(f"clamp {resource}")
        elif effect.type == "multiply_resource":
            resource = _RESOURCE_LABELS.get(
                params.get("resource"), str(params.get("resource"))
            )
            factor = _format_value(params.get("factor"), state, data)
            parts.append(f"{resource} x{factor}")
        elif effect.type == "add_status":
            parts.append(f"status {params.get('status')}")
        elif effect.type == "remove_status":
            parts.append(f"remove {params.get('status')}")
        elif effect.type == "add_flag":
            parts.append(f"flag {params.get('flag')}")
        elif effect.type == "remove_flag":
            parts.append(f"remove {params.get('flag')}")
        elif effect.type == "require_next_action":
            parts.append(f"require next {params.get('action')}")
        elif effect.type == "end_run":
            parts.append("end run")
        elif effect.type == "raw_effect":
            raw = params.get("raw")
            if raw:
                parts.append(str(raw))
    return parts


def _format_delta(amount, state: GameState, data: JusticeData) -> str:
    value = _resolve_amount(amount, state, data)
    if value is None:
        return str(amount)
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:g}"


def _format_value(amount, state: GameState, data: JusticeData) -> str:
    value = _resolve_amount(amount, state, data)
    if value is None:
        return str(amount)
    return f"{value:g}"


def _resolve_amount(
    amount: object, state: GameState, data: JusticeData
) -> float | None:
    if amount is None:
        return None
    try:
        return float(resolve_expr(amount, state, data))
    except Exception:
        return None
