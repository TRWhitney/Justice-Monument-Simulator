"""UI scaling helpers for Qt widgets."""

from __future__ import annotations

UI_SCALE_MODES = ("auto", "small", "medium", "large")
UI_SCALE_PRESETS = {
    "small": 1.0,
    "medium": 1.15,
    "large": 1.3,
}
UI_SCALE_LABELS = {
    "auto": "Auto (adaptive)",
    "small": "Small",
    "medium": "Medium",
    "large": "Large",
}


def next_ui_scale(current: str) -> str:
    """Return the next UI scale mode in the cycle."""
    if current not in UI_SCALE_MODES:
        return "auto"
    index = UI_SCALE_MODES.index(current)
    return UI_SCALE_MODES[(index + 1) % len(UI_SCALE_MODES)]


def resolve_ui_scale(mode: str, *, dpi: float | None) -> float:
    """Resolve a scale factor for the requested mode."""
    if mode == "auto":
        base = (dpi / 96.0) if dpi and dpi > 0 else 1.0
        return max(1.1, base)
    return UI_SCALE_PRESETS.get(mode, UI_SCALE_PRESETS["small"])


def scale_int(value: int, scale: float, *, minimum: int | None = None) -> int:
    scaled = int(round(value * scale))
    if minimum is not None:
        return max(minimum, scaled)
    return scaled
