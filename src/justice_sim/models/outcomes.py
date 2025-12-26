"""Outcome-related helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from justice_sim.models.offer import OutcomeSpec


@dataclass(frozen=True)
class OutcomeResult:
    outcome: OutcomeSpec
    random_label: str | None = None
    extra: dict[str, Any] | None = None
