"""Run state import/export."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from justice_sim.engine.rng import RngState
from justice_sim.models.offer import EffectSpec
from justice_sim.models.state import (
    ActionTrigger,
    EncounterModifier,
    EncounterOverride,
    EncounterTrigger,
    ForcedEncounter,
    GameState,
    ScheduledEvent,
    StatusEffect,
)


@dataclass(frozen=True)
class RunState:
    version: str
    state: GameState
    rng_state: RngState
    log: list[dict[str, Any]]


def save_run_state(path: Path, run_state: RunState) -> None:
    payload = {
        "version": run_state.version,
        "state": serialize_state(run_state.state),
        "rng_state": {
            "seed": run_state.rng_state.seed,
            "draws": run_state.rng_state.draws,
        },
        "log": run_state.log,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_run_state(path: Path) -> RunState:
    payload = json.loads(path.read_text(encoding="utf-8"))
    state = deserialize_state(payload["state"])
    rng_state = RngState(
        seed=int(payload["rng_state"]["seed"]), draws=int(payload["rng_state"]["draws"])
    )
    return RunState(
        version=str(payload.get("version", "run_state_v1")),
        state=state,
        rng_state=rng_state,
        log=list(payload.get("log", [])),
    )


def serialize_state(state: GameState) -> dict[str, Any]:
    return {
        "case_index": state.case_index,
        "coins": state.coins,
        "pop": state.pop,
        "mh": state.mh,
        "dismissals": state.dismissals,
        "retirement_chests": state.retirement_chests,
        "flags": sorted(state.flags),
        "statuses": {
            name: {"remaining_cases": status.remaining_cases, "data": dict(status.data)}
            for name, status in state.statuses.items()
        },
        "scheduled_events": [
            {
                "trigger_case_index": event.trigger_case_index,
                "effects": [_serialize_effect(effect) for effect in event.effects],
                "label": event.label,
            }
            for event in state.scheduled_events
        ],
        "encounter_modifiers": [
            {
                "npc_weights": dict(modifier.npc_weights or {}),
                "offer_weights": dict(modifier.offer_weights or {}),
                "mode": modifier.mode,
                "remaining_cases": modifier.remaining_cases,
            }
            for modifier in state.encounter_modifiers
        ],
        "forced_encounters": [
            {
                "trigger_case_index": forced.trigger_case_index,
                "offer_id": forced.offer_id,
                "once": forced.once,
            }
            for forced in state.forced_encounters
        ],
        "required_action": state.required_action,
        "required_action_penalty_effects": [
            _serialize_effect(effect)
            for effect in state.required_action_penalty_effects
        ],
        "counters": dict(state.counters),
        "resource_floors": dict(state.resource_floors),
        "action_triggers": [
            {
                "label": trigger.label,
                "action": trigger.action,
                "npc_id": trigger.npc_id,
                "offer_id": trigger.offer_id,
                "remaining_uses": trigger.remaining_uses,
                "when": trigger.when,
                "effects": [_serialize_effect(effect) for effect in trigger.effects],
            }
            for trigger in state.action_triggers
        ],
        "encounter_triggers": [
            {
                "label": trigger.label,
                "npc_id": trigger.npc_id,
                "offer_id": trigger.offer_id,
                "remaining_uses": trigger.remaining_uses,
                "when": trigger.when,
                "effects": [_serialize_effect(effect) for effect in trigger.effects],
            }
            for trigger in state.encounter_triggers
        ],
        "encounter_overrides": [
            {
                "label": override.label,
                "npc_id": override.npc_id,
                "offer_id": override.offer_id,
                "remaining_uses": override.remaining_uses,
                "probability": override.probability,
                "priority": override.priority,
                "allow_harbinger": override.allow_harbinger,
            }
            for override in state.encounter_overrides
        ],
        "ended": state.ended,
        "end_reason": state.end_reason,
    }


def deserialize_state(payload: Mapping[str, Any]) -> GameState:
    statuses = {
        name: StatusEffect(
            name=name,
            remaining_cases=int(item["remaining_cases"]),
            data=item.get("data", {}),
        )
        for name, item in payload.get("statuses", {}).items()
    }
    scheduled_events = tuple(
        ScheduledEvent(
            trigger_case_index=int(event["trigger_case_index"]),
            effects=tuple(
                _deserialize_effect(effect) for effect in event.get("effects", [])
            ),
            label=event.get("label"),
        )
        for event in payload.get("scheduled_events", [])
    )
    modifiers = tuple(
        EncounterModifier(
            npc_weights=modifier.get("npc_weights"),
            offer_weights=modifier.get("offer_weights"),
            mode=modifier.get("mode", "multiply"),
            remaining_cases=modifier.get("remaining_cases"),
        )
        for modifier in payload.get("encounter_modifiers", [])
    )
    forced = tuple(
        ForcedEncounter(
            trigger_case_index=int(item["trigger_case_index"]),
            offer_id=str(item["offer_id"]),
            once=bool(item.get("once", True)),
        )
        for item in payload.get("forced_encounters", [])
    )
    required_penalties = tuple(
        _deserialize_effect(effect)
        for effect in payload.get("required_action_penalty_effects", [])
    )
    action_triggers = tuple(
        ActionTrigger(
            label=item.get("label"),
            action=str(item.get("action", "")),
            npc_id=item.get("npc_id"),
            offer_id=item.get("offer_id"),
            remaining_uses=item.get("remaining_uses"),
            when=item.get("when"),
            effects=tuple(
                _deserialize_effect(effect) for effect in item.get("effects", [])
            ),
        )
        for item in payload.get("action_triggers", [])
    )
    encounter_triggers = tuple(
        EncounterTrigger(
            label=item.get("label"),
            npc_id=item.get("npc_id"),
            offer_id=item.get("offer_id"),
            remaining_uses=item.get("remaining_uses"),
            when=item.get("when"),
            effects=tuple(
                _deserialize_effect(effect) for effect in item.get("effects", [])
            ),
        )
        for item in payload.get("encounter_triggers", [])
    )
    encounter_overrides = tuple(
        EncounterOverride(
            label=item.get("label"),
            npc_id=item.get("npc_id"),
            offer_id=item.get("offer_id"),
            remaining_uses=item.get("remaining_uses"),
            probability=item.get("probability"),
            priority=int(item.get("priority", 0) or 0),
            allow_harbinger=bool(item.get("allow_harbinger", False)),
        )
        for item in payload.get("encounter_overrides", [])
    )
    return GameState(
        case_index=int(payload.get("case_index", 1)),
        coins=float(payload.get("coins", 0)),
        pop=float(payload.get("pop", 0)),
        mh=float(payload.get("mh", 1)),
        dismissals=float(payload.get("dismissals", 0)),
        retirement_chests=float(payload.get("retirement_chests", 0)),
        flags=frozenset(payload.get("flags", [])),
        statuses=statuses,
        scheduled_events=scheduled_events,
        encounter_modifiers=modifiers,
        forced_encounters=forced,
        required_action=payload.get("required_action"),
        required_action_penalty_effects=required_penalties,
        counters=payload.get("counters", {}),
        resource_floors=payload.get("resource_floors", {}),
        action_triggers=action_triggers,
        encounter_triggers=encounter_triggers,
        encounter_overrides=encounter_overrides,
        ended=bool(payload.get("ended", False)),
        end_reason=payload.get("end_reason"),
    )


def _serialize_effect(effect: EffectSpec) -> dict[str, Any]:
    return {
        "type": effect.type,
        "params": dict(effect.params),
        "when": effect.when,
        "duration_cases": effect.duration_cases,
        "schedule_after_cases": effect.schedule_after_cases,
        "label": effect.label,
    }


def _deserialize_effect(payload: Mapping[str, Any]) -> EffectSpec:
    return EffectSpec(
        type=str(payload.get("type")),
        params=dict(payload.get("params", {})),
        when=payload.get("when"),
        duration_cases=payload.get("duration_cases"),
        schedule_after_cases=payload.get("schedule_after_cases"),
        label=payload.get("label"),
    )
