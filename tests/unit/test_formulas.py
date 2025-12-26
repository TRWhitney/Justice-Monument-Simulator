import math

import pytest

from justice_sim.engine.harbinger import (
    case_scale,
    gratefulbinger_replace_probability,
    harbinger_cost,
)


@pytest.mark.unit
def test_case_scale_matches_spec():
    for case_index in range(1, 31):
        assert case_scale(case_index) == math.ceil(case_index / 5)


@pytest.mark.unit
def test_harbinger_cost_spot_checks():
    assert harbinger_cost(1) == pytest.approx(1.0)
    assert harbinger_cost(5) == pytest.approx(1.0)
    assert harbinger_cost(13) == pytest.approx(3.0)
    assert harbinger_cost(14) == pytest.approx(3.75)
    assert harbinger_cost(26) == pytest.approx(7.5)


@pytest.mark.unit
def test_gratefulbinger_replace_probability():
    assert gratefulbinger_replace_probability(0) == 0.0
    assert gratefulbinger_replace_probability(20) == pytest.approx(0.2)
    assert gratefulbinger_replace_probability(80) == pytest.approx(0.32)
