from dataclasses import replace

import pytest

from justice_sim.engine.effects import advance_case
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import GameState, ScheduledEvent, StatusEffect
from justice_sim.planner.rollout import RolloutPlanner

pytestmark = pytest.mark.unit


def test_cache_distinguishes_conditional_pending_payments(data_factory):
    data = data_factory(include_grateful=False)
    payment = EffectSpec(
        "add_resource", {"resource": "coins", "amount": 10}, when="pop > 0"
    )
    state = GameState(
        4, 0, 1, 3, 0, 0, scheduled_events=(ScheduledEvent(5, (payment,)),)
    )
    other = replace(
        state,
        scheduled_events=(ScheduledEvent(5, (replace(payment, when="pop < 0"),)),),
    )
    planner = RolloutPlanner.from_defaults(data, seed=1)
    assert state.to_cache_key() != other.to_cache_key()
    assert planner._cached_utility(state) != planner._cached_utility(other)


def test_cache_preserves_scheduled_event_order_and_labels(data_factory):
    data = data_factory()
    set_coins = ScheduledEvent(
        2, (EffectSpec("set_resource", {"resource": "coins", "value": 1}),)
    )
    double_coins = ScheduledEvent(
        2, (EffectSpec("multiply_resource", {"resource": "coins", "factor": 2}),)
    )
    state = GameState(1, 5, 3, 3, 0, 0, scheduled_events=(set_coins, double_coins))
    reversed_state = replace(state, scheduled_events=(double_coins, set_coins))
    assert advance_case(state, data).coins != advance_case(reversed_state, data).coins
    assert state.to_cache_key() != reversed_state.to_cache_key()
    labeled = replace(
        state, scheduled_events=(replace(set_coins, label="pending_deal"), double_coins)
    )
    assert state.to_cache_key() != labeled.to_cache_key()


def test_nested_status_payload_is_hashable():
    state = GameState(
        1,
        5,
        3,
        3,
        0,
        0,
        statuses={
            "contract": StatusEffect(
                "contract", 2, {"effects": [{"resource": "coins"}]}
            )
        },
    )
    assert {state.to_cache_key(): 1}[state.to_cache_key()] == 1
