import pytest

from justice_sim.ui_qt.widgets import offer_card


@pytest.mark.unit
def test_highlight_text_wraps_matches():
    html_text = offer_card._highlight_text("Alpha beta gamma", ["beta"])
    assert html_text.count("<span") == 1
    assert "Alpha" in html_text
    assert "beta" in html_text
    assert "gamma" in html_text


@pytest.mark.unit
def test_highlight_text_is_case_insensitive_and_multiple():
    html_text = offer_card._highlight_text("Scripticus thinks", ["SCRIPT", "think"])
    assert html_text.count("<span") == 2
    assert "Script" in html_text
    assert "think" in html_text
