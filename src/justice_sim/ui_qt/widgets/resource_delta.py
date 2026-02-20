"""Resource delta formatting for Qt widgets."""

from __future__ import annotations

import html
from pathlib import Path

from justice_sim.models.state import GameState


_RESOURCE_ICONS = {
    "coins": "court_coin.png",
    "pop": "pop.png",
    "mh": "mental_health.png",
    "dismissals": "dismissal.png",
    "retirement_chests": "chest.png",
}


def format_resource_delta_html(
    before: GameState,
    after: GameState,
    icon_size: int = 18,
    *,
    action: str | None = None,
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
        delta_text = _format_delta(delta)
        icon_name = _RESOURCE_ICONS.get(resource)
        icon_path = _resolve_icon_path(icon_name) if icon_name else None
        if icon_path:
            icon_html = (
                f'<img src="{html.escape(str(icon_path))}" '
                f'width="{icon_size}" height="{icon_size}">'
            )
            parts.append(f"{icon_html} {html.escape(delta_text)}")
        else:
            parts.append(f"{html.escape(resource)} {html.escape(delta_text)}")
    if parts:
        return "  ".join(parts)
    if action == "skip":
        return "No effect (skip)"
    return "No effect"


def _resolve_icon_path(filename: str | None) -> Path | None:
    if not filename:
        return None
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "src" / "justice_sim" / "data" / "builtin" / "images" / filename
    return path if path.exists() else None


def _format_delta(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    abs_value = abs(value)
    return f"{sign}{abs_value:g}"
