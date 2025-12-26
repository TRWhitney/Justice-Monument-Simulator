"""Deterministic RNG wrapper with draw counting."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RngState:
    seed: int
    draws: int


class Rng:
    def __init__(self, seed: int | None = None) -> None:
        if seed is None:
            seed = random.randrange(1, 2**31)
        self._seed = int(seed)
        self._random = random.Random(self._seed)
        self._draws = 0

    @property
    def seed(self) -> int:
        return self._seed

    def random(self) -> float:
        self._draws += 1
        return self._random.random()

    def randint(self, a: int, b: int) -> int:
        self._draws += 1
        return self._random.randint(a, b)

    def choice(self, seq: Iterable[Any]) -> Any:
        seq_list = list(seq)
        if not seq_list:
            raise ValueError("Cannot choose from empty sequence")
        index = int(self.random() * len(seq_list))
        return seq_list[min(index, len(seq_list) - 1)]

    def weighted_choice(self, choices: list[tuple[Any, float]]) -> Any:
        total = sum(weight for _, weight in choices)
        if total <= 0:
            raise ValueError("Total weight must be positive")
        threshold = self.random() * total
        cumulative = 0.0
        for item, weight in choices:
            cumulative += weight
            if threshold <= cumulative:
                return item
        return choices[-1][0]

    def state(self) -> RngState:
        return RngState(seed=self._seed, draws=self._draws)

    def advance(self, draws: int) -> None:
        for _ in range(draws):
            self.random()

    def spawn(self, token: int) -> "Rng":
        derived_seed = (self._seed * 6364136223846793005 + token) % (2**31 - 1)
        return Rng(int(derived_seed))

    @staticmethod
    def from_state(state: RngState) -> "Rng":
        rng = Rng(state.seed)
        rng.advance(state.draws)
        return rng
