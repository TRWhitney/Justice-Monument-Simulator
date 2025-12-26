"""Planner caching utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from justice_sim.models.state import GameState


@dataclass
class ValueCache:
    max_entries: int = 10000
    _store: dict[tuple[Any, ...], float] = field(default_factory=dict)

    def get(self, state: GameState, remaining_depth: int) -> float | None:
        return self._store.get((state.to_cache_key(), remaining_depth))

    def set(self, state: GameState, remaining_depth: int, value: float) -> None:
        key = (state.to_cache_key(), remaining_depth)
        if len(self._store) >= self.max_entries:
            self._store.pop(next(iter(self._store)))
        self._store[key] = value
