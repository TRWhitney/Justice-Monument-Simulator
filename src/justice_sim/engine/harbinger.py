"""Harbinger-related formulas."""

from __future__ import annotations

import math


def case_scale(case_index: int) -> int:
    return math.ceil(case_index / 5)


def harbinger_cost(case_index: int) -> float:
    return case_scale(case_index) * (1 + 0.25 * math.floor((case_index - 1) / 13))


def gratefulbinger_replace_probability(pop: float) -> float:
    if pop <= 0:
        return 0.0
    return (40 * pop) / (pop + 20) / 100.0
