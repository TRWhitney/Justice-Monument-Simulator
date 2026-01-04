from __future__ import annotations

from PySide6 import QtCore

from justice_sim.ui_qt.prefs import (
    KEY_SCALE_MODE,
    KEY_THEME_DARK,
    load_ui_prefs,
    save_ui_prefs,
)


def test_ui_prefs_round_trip(tmp_path) -> None:
    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    settings = QtCore.QSettings(
        str(tmp_path / "prefs.ini"), QtCore.QSettings.Format.IniFormat
    )
    theme, scale = load_ui_prefs(settings)
    assert theme is False
    assert scale == "auto"

    save_ui_prefs(settings, theme_dark=True, scale_mode="large")
    theme, scale = load_ui_prefs(settings)
    assert theme is True
    assert scale == "large"


def test_ui_prefs_invalid_scale_falls_back(tmp_path) -> None:
    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    settings = QtCore.QSettings(
        str(tmp_path / "prefs.ini"), QtCore.QSettings.Format.IniFormat
    )
    settings.setValue(KEY_THEME_DARK, True)
    settings.setValue(KEY_SCALE_MODE, "giant")
    theme, scale = load_ui_prefs(settings, default_scale="auto")
    assert theme is True
    assert scale == "auto"
