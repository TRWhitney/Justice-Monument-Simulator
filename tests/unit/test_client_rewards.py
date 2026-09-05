"""Behavioral fixtures from the pinned September 2026 official client."""

from dataclasses import replace

import pytest

from justice_sim.engine.reducer import (
    apply_action,
    can_afford_action,
)
from justice_sim.engine.rng import Rng
from justice_sim.models.state import GameState

pytestmark = pytest.mark.unit


class Draw(Rng):
    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        self._draws += 1
        return self.value


def offer(data, row):
    return next(o for o in data.offers if row in o.client_rows)


def state(**changes):
    return replace(GameState(1, 20, 20, 5, 3, 7), **changes)


def act(data, row, action="approve", draw=0.1, **changes):
    return apply_action(state(**changes), offer(data, row), action, data, Draw(draw))[0]


@pytest.mark.parametrize(
    "row,coins,pop,chests,dismissals,allowed",
    [
        (18, 0, 0, 0, 0, True),
        (16, 3, 0, 0, 0, True),
        (48, 0, 0, 0, 0, True),
        (67, 0, 0, 0, 0, True),
        (11, 0, 20, 0, 0, False),
        (51, 0, 0, 1, 0, True),
        (51, 0, 20, 0, 0, False),
        (68, 0, 0, 0, 0, False),
        (68, 0, 0, 0, 1, True),
    ],
)
def test_client_payment_gates(
    builtin_data, row, coins, pop, chests, dismissals, allowed
):
    s = state(coins=coins, pop=pop, retirement_chests=chests, dismissals=dismissals)
    assert (
        can_afford_action(s, offer(builtin_data, row), "approve", builtin_data)
        is allowed
    )


def test_bean_bonus_precedes_final_resource_clamp(builtin_data):
    s = act(builtin_data, 29, coins=0)
    assert s.coins == 4
    s = replace(s, coins=0)
    s, _ = apply_action(s, offer(builtin_data, 23), "approve", builtin_data, Draw(0.1))
    assert s.coins == 2  # Bonus 4, then the two-coin payment; no premature clamp.
