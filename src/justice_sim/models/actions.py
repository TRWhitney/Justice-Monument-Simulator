"""Action constants."""

from __future__ import annotations

from typing import Literal

Action = Literal["approve", "reject", "dismiss"]

ACTIONS: tuple[Action, ...] = ("approve", "reject", "dismiss")
