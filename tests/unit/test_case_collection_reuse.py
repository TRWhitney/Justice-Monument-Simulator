"""Case progression retains unchanged collections and replaces changed ones."""

from dataclasses import replace

import pytest

from justice_sim.engine.effects import advance_case, apply_effects
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import (
    EncounterModifier,
    GameState,
    ScheduledEvent,
    StatusEffect,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("populated", [False, True])
def test_unchanged_collections_are_shared_without_mutating_prior_states(
    data_factory, populated
):
    data = data_factory()
    state = GameState(5, 10, 3, 3, 0, 0)
    if populated:
        state = replace(
            state,
            statuses={"permanent": StatusEffect("permanent", -1)},
            encounter_modifiers=(EncounterModifier(npc_weights={"npc1": 2}),),
            scheduled_events=(
                ScheduledEvent(
                    10,
                    (EffectSpec("add_resource", {"resource": "coins", "amount": 5}),),
                ),
            ),
        )
    rng = Rng(42)
    advanced = advance_case(state, data, rng)
    assert advanced.case_index == 6
    assert advanced.statuses is state.statuses
    assert advanced.encounter_modifiers is state.encounter_modifiers
    assert advanced.scheduled_events is state.scheduled_events
    assert rng.state().draws == 0
    changed = apply_effects(
        advanced, (EffectSpec("add_status", {"status": "new"}, duration_cases=2),), data
    )
    assert "new" in changed.statuses and "new" not in state.statuses


def test_timed_changes_copy_only_affected_collections_and_keep_order(data_factory):
    permanent = StatusEffect("permanent", -1)
    timed = StatusEffect("timed", 2)
    permanent_modifier = EncounterModifier(npc_weights={"npc1": 2})
    timed_modifier = EncounterModifier(npc_weights={"npc2": 3}, remaining_cases=2)
    expired_modifier = EncounterModifier(remaining_cases=1)
    state = GameState(
        5,
        10,
        3,
        3,
        0,
        0,
        statuses={
            "permanent": permanent,
            "timed": timed,
            "expired": StatusEffect("expired", 1),
        },
        encounter_modifiers=(
            permanent_modifier,
            timed_modifier,
            expired_modifier,
            permanent_modifier,
        ),
    )
    advanced = advance_case(state, data_factory())
    assert advanced.statuses is not state.statuses
    assert advanced.statuses == {
        "permanent": permanent,
        "timed": replace(timed, remaining_cases=1),
    }
    assert advanced.statuses["permanent"] is permanent
    assert advanced.encounter_modifiers == (
        permanent_modifier,
        replace(timed_modifier, remaining_cases=1),
        permanent_modifier,
    )
    assert advanced.encounter_modifiers[0] is permanent_modifier
    assert advanced.encounter_modifiers[-1] is permanent_modifier
    assert advanced.scheduled_events is state.scheduled_events
    assert state.statuses["timed"].remaining_cases == 2
    assert len(state.encounter_modifiers) == 4


def test_new_status_waits_one_case_before_countdown(data_factory):
    state = GameState(
        5,
        10,
        3,
        3,
        0,
        0,
        statuses={
            "new": StatusEffect(
                "new", 2, {"starts_next_case": True, "applied_case_index": 5}
            )
        },
    )
    first = advance_case(state, data_factory())
    assert first.statuses is state.statuses
    second = advance_case(first, data_factory())
    assert second.statuses is not first.statuses
    assert second.statuses["new"].remaining_cases == 1
    assert first.statuses["new"].remaining_cases == 2


def test_due_events_preserve_execution_and_remaining_order(data_factory):
    future = ScheduledEvent(10, (EffectSpec("end_run", {}),), "future")
    set_coins = ScheduledEvent(
        6, (EffectSpec("set_resource", {"resource": "coins", "value": 2}),), "first"
    )
    double = ScheduledEvent(
        6,
        (EffectSpec("multiply_resource", {"resource": "coins", "factor": 3}),),
        "second",
    )
    state = GameState(
        5, 10, 3, 3, 0, 0, scheduled_events=(future, set_coins, future, double)
    )
    advanced = advance_case(state, data_factory())
    assert advanced.coins == 6
    assert advanced.scheduled_events == (future, future)
    assert all(event is future for event in advanced.scheduled_events)
    assert advanced.statuses is state.statuses
    assert advanced.encounter_modifiers is state.encounter_modifiers
    assert len(state.scheduled_events) == 4


def test_due_random_event_preserves_draws_and_newly_scheduled_events(data_factory):
    effects = (
        EffectSpec("random_range_resource", {"resource": "coins", "min": 2, "max": 8}),
        EffectSpec(
            "schedule_effects",
            {
                "after_cases": 2,
                "effects": [
                    {"type": "add_resource", "params": {"resource": "mh", "amount": -1}}
                ],
            },
        ),
    )
    state = GameState(5, 10, 3, 3, 0, 0, scheduled_events=(ScheduledEvent(6, effects),))
    rng = Rng(42)
    advanced = advance_case(state, data_factory(), rng)
    reference_rng = Rng(42)
    expected = apply_effects(
        replace(state, case_index=6, scheduled_events=()),
        effects,
        data_factory(),
        reference_rng,
    )
    assert advanced == expected
    assert rng.state() == reference_rng.state()
    assert advanced.scheduled_events[0].trigger_case_index == 8
