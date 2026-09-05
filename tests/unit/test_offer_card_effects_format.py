import pytest

from justice_sim.ui_qt.widgets import offer_card
from justice_sim.models.state import GameState
from justice_sim.util.immutable import freeze_payload


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


@pytest.mark.unit
def test_effects_html_custom_separator_respected():
    tokens = [("coins", "+ 1", ""), ("pop", "+ 2", " OR ")]
    html_text = offer_card._format_effects_html(tokens, "no effect")
    assert "OR" in html_text
    assert html_text.count("<img") == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "formatter", [offer_card._format_amount_text, offer_card._format_value_text]
)
def test_frozen_amounts_preserve_values_and_unresolved_expression_text(
    data_factory, formatter
):
    data = data_factory()
    state = GameState(1, 5, 3, 3, 0, 0)
    for expression in ("coins + 2", "unknown_name"):
        raw = {"expr": expression}
        assert formatter(freeze_payload(raw), data, state) == formatter(
            raw, data, state
        )
