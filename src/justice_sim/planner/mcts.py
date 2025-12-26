"""Placeholder for future MCTS implementation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MctsConfig:
    iterations: int = 1000


class MctsPlanner:
    def __init__(self, config: MctsConfig | None = None) -> None:
        self.config = config or MctsConfig()

    def recommend(self, *args, **kwargs):  # pragma: no cover - placeholder
        raise NotImplementedError("MCTS planner not implemented yet")
