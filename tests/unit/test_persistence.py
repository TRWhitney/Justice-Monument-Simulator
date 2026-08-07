from __future__ import annotations

import pytest

from justice_sim.engine.rng import RngState
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import (
    EncounterModifier,
    ForcedEncounter,
    GameState,
    ScheduledEvent,
    StatusEffect,
)
from justice_sim.persistence.logs import SessionLog
from justice_sim.engine.luck import EncounterLuck
from justice_sim.persistence.profiles import Profile, load_profile, save_profile
from justice_sim.persistence.runs import (
    RunState,
    load_run_state,
    save_run_state,
    serialize_state,
)


@pytest.mark.unit
def test_run_state_roundtrip(tmp_path):
    state = GameState(
        case_index=3,
        coins=5,
        pop=1,
        mh=2,
        dismissals=1,
        retirement_chests=1,
        flags=frozenset({"flag1"}),
        statuses={
            "status": StatusEffect(name="status", remaining_cases=2, data={"x": 1})
        },
        scheduled_events=(
            ScheduledEvent(
                trigger_case_index=4,
                effects=(
                    EffectSpec(
                        type="add_resource", params={"resource": "coins", "amount": 1}
                    ),
                ),
                label="test",
            ),
        ),
        encounter_modifiers=(
            EncounterModifier(
                npc_weights={"npc": 0.5}, mode="multiply", remaining_cases=1
            ),
        ),
        forced_encounters=(
            ForcedEncounter(trigger_case_index=4, offer_id="offer", once=True),
        ),
        required_action="approve",
        required_action_penalty_effects=(
            EffectSpec(type="add_resource", params={"resource": "mh", "amount": -1}),
        ),
        counters={"npc_rejects": 2},
    )
    run_state = RunState(
        version="run_state_v1", state=state, rng_state=RngState(1, 3), log=[]
    )
    path = tmp_path / "run.json"
    save_run_state(path, run_state)

    loaded = load_run_state(path)
    assert serialize_state(loaded.state) == serialize_state(state)
    assert loaded.rng_state.seed == 1
    assert loaded.rng_state.draws == 3


@pytest.mark.unit
def test_session_log_undo():
    log = SessionLog()
    state = GameState(
        case_index=1, coins=0, pop=0, mh=1, dismissals=0, retirement_chests=0
    )
    next_state = GameState(
        case_index=2, coins=1, pop=0, mh=1, dismissals=0, retirement_chests=0
    )
    log.record(state, "offer", "approve", RngState(1, 1), next_state)
    undone = log.undo()
    assert undone == state
    assert not log.entries


@pytest.mark.unit
def test_session_log_manual_adjust_merges_consecutive():
    log = SessionLog()
    pre_state = GameState(
        case_index=1, coins=1, pop=0, mh=1, dismissals=0, retirement_chests=0
    )
    mid_state = GameState(
        case_index=1, coins=2, pop=0, mh=1, dismissals=0, retirement_chests=0
    )
    post_state = GameState(
        case_index=1, coins=2, pop=1, mh=1, dismissals=0, retirement_chests=0
    )
    log.record_manual_adjust(pre_state, mid_state, RngState(1, 0))
    log.record_manual_adjust(mid_state, post_state, RngState(1, 0))

    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry.action == "adjust"
    assert entry.pre_state == pre_state
    assert entry.post_state == post_state


@pytest.mark.unit
def test_profile_roundtrip(tmp_path):
    profile = Profile(
        version="profile_v1",
        progression={"level": 2},
        planner_settings={"horizon_cases": 5},
    )
    path = tmp_path / "profile.json"
    save_profile(path, profile)
    loaded = load_profile(path)
    assert loaded.progression["level"] == 2
    assert loaded.planner_settings["horizon_cases"] == 5


@pytest.mark.unit
def test_session_log_roundtrip_preserves_encounter_luck():
    log = SessionLog()
    state = GameState(
        case_index=1, coins=5, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    post_state = GameState(
        case_index=2, coins=7, pop=3, mh=1, dismissals=0, retirement_chests=0
    )
    log.record(
        state,
        "offer1",
        "approve",
        RngState(1, 0),
        post_state,
        encounter_luck=EncounterLuck(rank=2, total=6),
    )

    reloaded = SessionLog.from_list(log.to_list())
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].encounter_luck == EncounterLuck(rank=2, total=6)
