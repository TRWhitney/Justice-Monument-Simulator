"""Game state and runtime entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Mapping, NamedTuple

from justice_sim.models.offer import EffectSpec
from justice_sim.util.immutable import freeze_payload, payload_key


@dataclass(frozen=True)
class StatusEffect:
    name: str
    remaining_cases: int
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", freeze_payload(self.data))


@dataclass(frozen=True)
class ScheduledEvent:
    trigger_case_index: int
    effects: tuple[EffectSpec, ...]
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", tuple(self.effects))

    @cached_property
    def cache_key(self) -> tuple:
        return (
            self.trigger_case_index,
            tuple(e.cache_key for e in self.effects),
            self.label,
        )


@dataclass(frozen=True)
class EncounterModifier:
    npc_weights: Mapping[str, float] | None = None
    offer_weights: Mapping[str, float] | None = None
    mode: str = "multiply"
    remaining_cases: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "npc_weights", freeze_payload(self.npc_weights))
        object.__setattr__(self, "offer_weights", freeze_payload(self.offer_weights))

    @cached_property
    def cache_key(self) -> tuple:
        return (
            self.mode,
            self.remaining_cases,
            payload_key(self.npc_weights or {}),
            payload_key(self.offer_weights or {}),
        )


@dataclass(frozen=True)
class ActionTrigger:
    action: str
    effects: tuple[EffectSpec, ...]
    npc_id: str | None = None
    offer_id: str | None = None
    remaining_uses: int | None = None
    when: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", tuple(self.effects))

    @cached_property
    def cache_key(self) -> tuple:
        return (
            self.label,
            self.action,
            self.npc_id,
            self.offer_id,
            self.remaining_uses,
            self.when,
            tuple(e.cache_key for e in self.effects),
        )


@dataclass(frozen=True)
class EncounterTrigger:
    effects: tuple[EffectSpec, ...]
    npc_id: str | None = None
    offer_id: str | None = None
    remaining_uses: int | None = None
    when: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effects", tuple(self.effects))

    @cached_property
    def cache_key(self) -> tuple:
        return (
            self.label,
            self.npc_id,
            self.offer_id,
            self.remaining_uses,
            self.when,
            tuple(e.cache_key for e in self.effects),
        )


@dataclass(frozen=True)
class EncounterOverride:
    npc_id: str | None = None
    offer_id: str | None = None
    remaining_uses: int | None = None
    probability: object | None = None
    priority: int = 0
    allow_harbinger: bool = False
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "probability", freeze_payload(self.probability))

    @cached_property
    def cache_key(self) -> tuple:
        return (
            self.label,
            self.npc_id,
            self.offer_id,
            self.remaining_uses,
            payload_key(self.probability),
            self.priority,
            self.allow_harbinger,
        )


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

        statuses_key = tuple(
            sorted(
                (name, status.remaining_cases, payload_key(status.data))
                for name, status in self.statuses.items()
            )
        )
        scheduled_key = tuple(event.cache_key for event in self.scheduled_events)
        modifiers_key = tuple(
            modifier.cache_key for modifier in self.encounter_modifiers
        )
        forced_key = tuple(
            (f.trigger_case_index, f.offer_id, f.once) for f in self.forced_encounters
        )
        action_triggers_key = tuple(t.cache_key for t in self.action_triggers)
        encounter_triggers_key = tuple(t.cache_key for t in self.encounter_triggers)
        encounter_overrides_key = tuple(o.cache_key for o in self.encounter_overrides)
        return ContractKey(
            statuses=statuses_key,
            scheduled_events=scheduled_key,
            encounter_modifiers=modifiers_key,
            forced_encounters=forced_key,
            required_action=self.required_action,
            required_action_penalty_effects=tuple(
                effect.cache_key for effect in self.required_action_penalty_effects
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
