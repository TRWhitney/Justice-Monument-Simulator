from dataclasses import replace

import pytest

from justice_sim.engine.effects import resolve_expr
from justice_sim.models.state import GameState

pytestmark = pytest.mark.unit


def test_case_scaling_keeps_resource_dependent_custom_formulas(data_factory):
    data = data_factory(cost_expr="coins + case_scale")
    data = replace(
        data,
        special_rules=replace(
            data.special_rules,
            case_scale=replace(data.special_rules.case_scale, expr="pop + case_index"),
        ),
    )
    for coins, pop in ((2, 3), (8, 1), (2, 3)):
        state = GameState(5, coins, pop, 3, 0, 0)
        assert resolve_expr({"expr": "2", "scaling": "harbinger"}, state, data) == 2 * (
            coins + pop + 5
        )
    other = data_factory(cost_expr="7 * case_scale")
    assert resolve_expr({"expr": "2", "scaling": "harbinger"}, state, other) == 14


@pytest.mark.parametrize(
    "expression",
    [
        "case_index / 3",
        {"expr": "-3", "scaling": "harbinger"},
        {"expr": "case_scale + harbinger_cost", "scaling": "case"},
        {"expr": "coins + case_scale", "scaling": "case"},
    ],
)
def test_cached_numeric_results_match_full_context(
    builtin_data, monkeypatch, expression
):
    from justice_sim.engine import effects

    states = [GameState(case, 50, 20, 8, 2, 0) for case in (1, 5, 11, 15, 30)]
    actual = [resolve_expr(expression, state, builtin_data) for state in states]
    monkeypatch.setattr(effects, "_case_only_scaling", lambda *args: False)
    expected = [resolve_expr(expression, state, builtin_data) for state in states]
    assert actual == expected
