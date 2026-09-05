"""Game state and runtime entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, NamedTuple

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


class ContractKey(NamedTuple):
    statuses: tuple
    scheduled_events: tuple
    encounter_modifiers: tuple
    forced_encounters: tuple
    required_action: str | None
    required_action_penalty_effects: tuple
    resource_floors: tuple
    action_triggers: tuple
    encounter_triggers: tuple
    encounter_overrides: tuple


class StateKey(NamedTuple):
    """Named fields retain the original full-state tuple's equality and order."""

    case_index: int
    coins: float
    pop: float
    mh: float
    dismissals: float
    retirement_chests: float
    flags: tuple
    statuses: tuple
    scheduled_events: tuple
    encounter_modifiers: tuple
    forced_encounters: tuple
    required_action: str | None
    required_action_penalty_effects: tuple
    counters: tuple
    resource_floors: tuple
    action_triggers: tuple
    encounter_triggers: tuple
    encounter_overrides: tuple
    ended: bool
    end_reason: str | None


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

    def contract_key(self) -> ContractKey:
        """Describe ordered contracts and their complete condition/effect payloads."""

        def freeze(value: Any) -> Any:
            if isinstance(value, Mapping):
                return tuple(sorted((k, freeze(v)) for k, v in value.items()))
            if isinstance(value, (list, tuple)):
                return tuple(freeze(v) for v in value)
            if isinstance(value, (set, frozenset)):
                return tuple(sorted(freeze(v) for v in value))
            return value

        def effect_key(effect: EffectSpec) -> tuple[Any, ...]:
            return (
                effect.type,
                freeze(effect.params),
                freeze(effect.when),
                effect.duration_cases,
                effect.schedule_after_cases,
                effect.label,
            )

        statuses_key = tuple(
            sorted(
                (name, status.remaining_cases, freeze(status.data))
                for name, status in self.statuses.items()
            )
        )
        scheduled_key = tuple(
            (
                event.trigger_case_index,
                tuple(effect_key(effect) for effect in event.effects),
                event.label,
            )
            for event in self.scheduled_events
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
                tuple(effect_key(effect) for effect in trigger.effects),
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
                tuple(effect_key(effect) for effect in trigger.effects),
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
        return ContractKey(
            statuses=statuses_key,
            scheduled_events=scheduled_key,
            encounter_modifiers=modifiers_key,
            forced_encounters=forced_key,
            required_action=self.required_action,
            required_action_penalty_effects=tuple(
                effect_key(effect) for effect in self.required_action_penalty_effects
            ),
            resource_floors=tuple(sorted(self.resource_floors.items())),
            action_triggers=action_triggers_key,
            encounter_triggers=encounter_triggers_key,
            encounter_overrides=encounter_overrides_key,
        )

    def to_cache_key(
        self,
        *,
        counter_names: frozenset[str] | None = None,
        contracts: ContractKey | None = None,
    ) -> StateKey:
        """Build a key from current values, optionally reusing this state's contracts."""
        return self._cache_key(counter_names, contracts, include_resources=True)

    def non_resource_key(self, counter_names: frozenset[str] | None = None) -> StateKey:
        """Compare future consequences without constructing a replacement state."""
        return self._cache_key(counter_names, None, include_resources=False)

    def _cache_key(
        self,
        counter_names: frozenset[str] | None,
        contracts: ContractKey | None,
        *,
        include_resources: bool,
    ) -> StateKey:
        contracts = self.contract_key() if contracts is None else contracts
        counters = self.counters.items()
        if counter_names is not None:
            counters = (
                (name, value) for name, value in counters if name in counter_names
            )
        return StateKey(
            case_index=self.case_index,
            coins=self.coins if include_resources else 0,
            pop=self.pop if include_resources else 0,
            mh=self.mh if include_resources else 0,
            dismissals=self.dismissals if include_resources else 0,
            retirement_chests=self.retirement_chests if include_resources else 0,
            flags=tuple(sorted(self.flags)),
            statuses=contracts.statuses,
            scheduled_events=contracts.scheduled_events,
            encounter_modifiers=contracts.encounter_modifiers,
            forced_encounters=contracts.forced_encounters,
            required_action=contracts.required_action,
            required_action_penalty_effects=contracts.required_action_penalty_effects,
            counters=tuple(sorted(counters)),
            resource_floors=contracts.resource_floors,
            action_triggers=contracts.action_triggers,
            encounter_triggers=contracts.encounter_triggers,
            encounter_overrides=contracts.encounter_overrides,
            ended=self.ended,
            end_reason=self.end_reason,
        )
