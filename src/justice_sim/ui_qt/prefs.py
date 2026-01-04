"""Qt UI preference persistence helpers."""

from __future__ import annotations

from PySide6 import QtCore

from justice_sim.ui_qt.ui_scale import UI_SCALE_MODES

KEY_THEME_DARK = "ui/theme_dark"
KEY_SCALE_MODE = "ui/scale_mode"
KEY_TOUR_SEEN = "ui/tour_seen"


def load_ui_prefs(
    settings: QtCore.QSettings,
    *,
    default_theme: bool = False,
    default_scale: str = "auto",
    allowed_modes: tuple[str, ...] = UI_SCALE_MODES,
) -> tuple[bool, str]:
    theme_dark = settings.value(KEY_THEME_DARK, default_theme, type=bool)
    scale_mode = settings.value(KEY_SCALE_MODE, default_scale, type=str)
    if scale_mode not in allowed_modes:
        scale_mode = default_scale
    return bool(theme_dark), scale_mode


def save_ui_prefs(
    settings: QtCore.QSettings, *, theme_dark: bool, scale_mode: str
) -> None:
    settings.setValue(KEY_THEME_DARK, bool(theme_dark))
    settings.setValue(KEY_SCALE_MODE, str(scale_mode))
    settings.sync()


def load_tour_seen(settings: QtCore.QSettings, *, default_seen: bool = False) -> bool:
    return bool(settings.value(KEY_TOUR_SEEN, default_seen, type=bool))


def save_tour_seen(settings: QtCore.QSettings, *, seen: bool) -> None:
    settings.setValue(KEY_TOUR_SEEN, bool(seen))
    settings.sync()
