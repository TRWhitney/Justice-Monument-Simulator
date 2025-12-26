import pytest

from justice_sim.ui_qt.widgets import offer_card


@pytest.mark.unit
def test_effects_html_capitalizes_and_separates():
    tokens = [("coins", "- 3"), ("", "other effect text here")]
    html_text = offer_card._format_effects_html(tokens, "no effect")
    assert "<img" in html_text
    assert "- 3" in html_text
    assert ", " in html_text
    assert "Other effect text here" in html_text


@pytest.mark.unit
def test_effects_html_no_effect_capitalized():
    html_text = offer_card._format_effects_html([], "no effect")
    assert html_text == "No effect"
