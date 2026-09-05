"""Behavioral fixtures from the pinned September 2026 official client."""

from dataclasses import replace
import math

import pytest

from justice_sim.engine.reducer import (
    apply_action,
    can_afford_action,
    preview_state_after_encounter_triggers,
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


@pytest.mark.parametrize("mh", [1, 2, 5])
@pytest.mark.parametrize("draw", [0.499999, 0.5])
def test_cool_bird_preserves_last_health(builtin_data, mh, draw):
    result = act(builtin_data, 54, mh=mh, draw=draw)
    assert result.mh == (mh + 2 if draw < 0.5 else max(1, mh - 1))


@pytest.mark.parametrize(
    "draw,resource,amount",
    [
        (0, "retirement_chests", 2),
        (0.29999, "retirement_chests", 2),
        (0.3, "retirement_chests", 3),
        (0.92999, "retirement_chests", 3),
        (0.93, "dismissals", 2),
        (0.96499, "dismissals", 2),
        (0.965, "coins", 2),
        (0.99999, "coins", 2),
    ],
)
def test_billionaire_reward_boundaries(builtin_data, draw, resource, amount):
    result = act(builtin_data, 80, draw=draw)
    for name in ("coins", "pop", "mh", "dismissals", "retirement_chests"):
        assert getattr(result, name) - getattr(state(), name) == (
            amount if name == resource else 0
        )


@pytest.mark.parametrize(
    "draw,pop_loss", [(0.1, 0), (0.3, 0), (0.5, 1), (0.7, 1), (0.9, 0)]
)
def test_grumblo_rejection_uses_hidden_row(builtin_data, draw, pop_loss):
    assert act(builtin_data, 44, "reject", draw=draw).pop == 20 - pop_loss


@pytest.mark.parametrize("row,coins,pop", [(65, 26, 16), (66, 16, 26)])
def test_rupie_exchanges_are_deterministic(builtin_data, row, coins, pop):
    for seed in range(5):
        rng = Rng(seed)
        result, _ = apply_action(
            state(), offer(builtin_data, row), "approve", builtin_data, rng
        )
        assert (result.coins, result.pop) == (coins, pop)
        assert rng.state().draws == 0


def test_rupie_exchange_includes_existing_bean_bonus(builtin_data):
    s = replace(act(builtin_data, 29), coins=20, pop=20)
    result, _ = apply_action(
        s, offer(builtin_data, 66), "approve", builtin_data, Draw(0.1)
    )
    assert (result.coins, result.pop) == (20, 27)


def test_life_insurance_preserves_chests(builtin_data):
    s = act(builtin_data, 72, mh=1)
    result = preview_state_after_encounter_triggers(
        s, offer(builtin_data, 2), builtin_data, Draw(0.1)
    )
    assert (result.coins, result.pop, result.mh, result.retirement_chests) == (
        1,
        1,
        1,
        7,
    )


@pytest.mark.parametrize("pop", [0, 1, 20, 23])
def test_poppy_role_model_snapshots_original_popularity(builtin_data, pop):
    s = act(builtin_data, 74, pop=pop)
    assert s.pop == 1
    s = replace(s, pop=7)
    result = preview_state_after_encounter_triggers(
        s, offer(builtin_data, 79), builtin_data, Draw(0.1)
    )
    assert result.pop == 7 + math.floor(1.6 * pop + 0.5)
    again = preview_state_after_encounter_triggers(
        result, offer(builtin_data, 79), builtin_data, Draw(0.1)
    )
    assert again == result


@pytest.mark.parametrize(
    "case,payment,repayment", [(1, 4, 6), (6, 8, 11), (11, 12, 17)]
)
def test_poppy_iou_pays_scripticus_once(builtin_data, case, payment, repayment):
    s = act(builtin_data, 75, case_index=case)
    assert s.coins == 20 - payment
    result = preview_state_after_encounter_triggers(
        s, offer(builtin_data, 23), builtin_data, Draw(0.1)
    )
    assert result.coins == 20 - payment + repayment
    assert (
        preview_state_after_encounter_triggers(
            result, offer(builtin_data, 23), builtin_data, Draw(0.1)
        )
        == result
    )


def test_broke_again_dismissal_still_costs_health(builtin_data):
    result = act(builtin_data, 15, "dismiss", mh=1, coins=0)
    assert (result.mh, result.dismissals) == (0, 2)


@pytest.mark.parametrize("case,pop", [(5, 20), (6, 19)])
def test_ghost_only_drains_ordinary_arrivals(builtin_data, case, pop):
    s = act(builtin_data, 50)
    assert s.pop == 20
    result = preview_state_after_encounter_triggers(
        replace(s, case_index=case), offer(builtin_data, 0), builtin_data, Draw(0.1)
    )
    assert result.pop == pop


def test_reinstating_ghost_ban_restores_arrival_loss(builtin_data):
    s = act(builtin_data, 50)
    result, _ = apply_action(
        s, offer(builtin_data, 59), "approve", builtin_data, Draw(0.1)
    )
    assert result.pop == 20
    assert not result.encounter_triggers


@pytest.mark.parametrize("coins,remaining", [(5, 2), (6, 3), (1, 0)])
def test_bean_halves_coins_downward(builtin_data, coins, remaining):
    assert act(builtin_data, 27, coins=coins).coins == remaining
