"""Game state and runtime entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from justice_sim.models.offer import EffectSpec


@dataclass(frozen=True)
class StatusEffect:
    name: str
    remaining_cases: int
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduledEvent:
    trigger_case_index: int
    effects: tuple[EffectSpec, ...]
    label: str | None = None


@dataclass(frozen=True)
class EncounterModifier:
    npc_weights: Mapping[str, float] | None = None
    offer_weights: Mapping[str, float] | None = None
    mode: str = "multiply"
    remaining_cases: int | None = None


@dataclass(frozen=True)
class ActionTrigger:
    action: str
    effects: tuple[EffectSpec, ...]
    npc_id: str | None = None
    offer_id: str | None = None
    remaining_uses: int | None = None
    when: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class EncounterTrigger:
    effects: tuple[EffectSpec, ...]
    npc_id: str | None = None
    offer_id: str | None = None
    remaining_uses: int | None = None
    when: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class EncounterOverride:
    npc_id: str | None = None
    offer_id: str | None = None
    remaining_uses: int | None = None
    probability: object | None = None
    priority: int = 0
    allow_harbinger: bool = False
    label: str | None = None


@dataclass(frozen=True)
class ForcedEncounter:
    trigger_case_index: int
    offer_id: str
    once: bool = True


@dataclass(frozen=True)
class GameState:
    case_index: int
    coins: float
    pop: float
    mh: float
    dismissals: float
    retirement_chests: float
    flags: frozenset[str] = field(default_factory=frozenset)
    statuses: Mapping[str, StatusEffect] = field(default_factory=dict)
    scheduled_events: tuple[ScheduledEvent, ...] = ()
    encounter_modifiers: tuple[EncounterModifier, ...] = ()
    forced_encounters: tuple[ForcedEncounter, ...] = ()
    required_action: str | None = None
    required_action_penalty_effects: tuple[EffectSpec, ...] = ()
    counters: Mapping[str, float] = field(default_factory=dict)
    resource_floors: Mapping[str, float] = field(default_factory=dict)
    action_triggers: tuple[ActionTrigger, ...] = ()
    encounter_triggers: tuple[EncounterTrigger, ...] = ()
    encounter_overrides: tuple[EncounterOverride, ...] = ()
    ended: bool = False
    end_reason: str | None = None

    def to_cache_key(self) -> tuple[Any, ...]:
        """Return a hashable key for planner caches."""

        def freeze(value: Any) -> Any:
            if isinstance(value, dict):
                return tuple(sorted((k, freeze(v)) for k, v in value.items()))
            if isinstance(value, (list, tuple)):
                return tuple(freeze(v) for v in value)
            if isinstance(value, set):
                return tuple(sorted(freeze(v) for v in value))
            return value

        statuses_key = tuple(
            sorted(
                (name, status.remaining_cases, tuple(sorted(status.data.items())))
                for name, status in self.statuses.items()
            )
        )
        scheduled_key = tuple(
            sorted(
                (
                    event.trigger_case_index,
                    tuple(
                        (effect.type, freeze(effect.params)) for effect in event.effects
                    ),
                )
                for event in self.scheduled_events
            )
        )
        modifiers_key = tuple(
            (
                modifier.mode,
                modifier.remaining_cases,
                tuple(sorted((modifier.npc_weights or {}).items())),
                tuple(sorted((modifier.offer_weights or {}).items())),
            )
            for modifier in self.encounter_modifiers
        )
        forced_key = tuple(
            (forced.trigger_case_index, forced.offer_id, forced.once)
            for forced in self.forced_encounters
        )
        action_triggers_key = tuple(
            (
                trigger.label,
                trigger.action,
                trigger.npc_id,
                trigger.offer_id,
                trigger.remaining_uses,
                trigger.when,
                tuple(
                    (effect.type, freeze(effect.params)) for effect in trigger.effects
                ),
            )
            for trigger in self.action_triggers
        )
        encounter_triggers_key = tuple(
            (
                trigger.label,
                trigger.npc_id,
                trigger.offer_id,
                trigger.remaining_uses,
                trigger.when,
                tuple(
                    (effect.type, freeze(effect.params)) for effect in trigger.effects
                ),
            )
            for trigger in self.encounter_triggers
        )
        encounter_overrides_key = tuple(
            (
                override.label,
                override.npc_id,
                override.offer_id,
                override.remaining_uses,
                freeze(override.probability),
                override.priority,
                override.allow_harbinger,
            )
            for override in self.encounter_overrides
        )
        counters_key = tuple(sorted(self.counters.items()))
        resource_floors_key = tuple(sorted(self.resource_floors.items()))
        return (
            self.case_index,
            self.coins,
            self.pop,
            self.mh,
            self.dismissals,
            self.retirement_chests,
            tuple(sorted(self.flags)),
            statuses_key,
            scheduled_key,
            modifiers_key,
            forced_key,
            self.required_action,
            tuple(
                (effect.type, freeze(effect.params))
                for effect in self.required_action_penalty_effects
            ),
            counters_key,
            resource_floors_key,
            action_triggers_key,
            encounter_triggers_key,
            encounter_overrides_key,
            self.ended,
            self.end_reason,
        )
