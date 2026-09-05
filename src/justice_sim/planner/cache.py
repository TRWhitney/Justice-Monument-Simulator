"""Planner caching utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from justice_sim.models.state import GameState


@dataclass
class ValueCache:
    max_entries: int = 10000
    _store: dict[tuple[Any, ...], float] = field(default_factory=dict)

    def get(self, state: GameState, remaining_depth: int) -> float | None:
        return self._store.get((state.to_cache_key(), remaining_depth))

    def set(self, state: GameState, remaining_depth: int, value: float) -> None:
        key = (state.to_cache_key(), remaining_depth)
        self.set_key(key, value)

    def set_key(self, key: tuple[Any, ...], value: float) -> None:
        if key not in self._store and len(self._store) >= self.max_entries:
            self._store.pop(next(iter(self._store)))
        self._store[key] = value

    def get_or_compute(
        self,
        state: GameState,
        remaining_depth: int,
        compute: Callable[[GameState], float],
    ) -> float:
        key = (state.to_cache_key(), remaining_depth)
        value = self._store.get(key)
        if value is None:
            value = compute(state)
            self.set_key(key, value)
        return value
