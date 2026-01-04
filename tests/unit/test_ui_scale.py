from __future__ import annotations

import pytest

from justice_sim.ui_qt.ui_scale import (
    UI_SCALE_PRESETS,
    next_ui_scale,
    resolve_ui_scale,
)


@pytest.mark.unit
def test_next_ui_scale_cycles() -> None:
    assert next_ui_scale("auto") == "small"
    assert next_ui_scale("small") == "medium"
    assert next_ui_scale("medium") == "large"
    assert next_ui_scale("large") == "auto"


@pytest.mark.unit
def test_resolve_ui_scale_presets() -> None:
    for mode, expected in UI_SCALE_PRESETS.items():
        assert resolve_ui_scale(mode, dpi=96) == pytest.approx(expected)


@pytest.mark.unit
def test_resolve_ui_scale_auto_minimum() -> None:
    assert resolve_ui_scale("auto", dpi=96) == pytest.approx(1.1)
    assert resolve_ui_scale("auto", dpi=120) == pytest.approx(120 / 96)
