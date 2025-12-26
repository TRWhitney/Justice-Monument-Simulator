"""Session log handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from justice_sim.engine.rng import RngState
from justice_sim.models.state import GameState
from justice_sim.persistence.runs import deserialize_state, serialize_state


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    pre_state: GameState
    offer_id: str
    action: str
    rng_state: RngState
    post_state: GameState
    random_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "pre_state": serialize_state(self.pre_state),
            "offer_id": self.offer_id,
            "action": self.action,
            "rng_state": {"seed": self.rng_state.seed, "draws": self.rng_state.draws},
            "post_state": serialize_state(self.post_state),
            "random_label": self.random_label,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "LogEntry":
        return LogEntry(
            timestamp=str(payload.get("timestamp")),
            pre_state=deserialize_state(payload["pre_state"]),
            offer_id=str(payload.get("offer_id")),
            action=str(payload.get("action")),
            rng_state=RngState(
                seed=int(payload["rng_state"]["seed"]),
                draws=int(payload["rng_state"]["draws"]),
            ),
            post_state=deserialize_state(payload["post_state"]),
            random_label=payload.get("random_label"),
        )


@dataclass
class SessionLog:
    entries: list[LogEntry] = field(default_factory=list)

    def record(
        self,
        pre_state: GameState,
        offer_id: str,
        action: str,
        rng_state: RngState,
        post_state: GameState,
        random_label: str | None = None,
    ) -> None:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            pre_state=pre_state,
            offer_id=offer_id,
            action=action,
            rng_state=rng_state,
            post_state=post_state,
            random_label=random_label,
        )
        self.entries.append(entry)

    def undo(self) -> GameState | None:
        if not self.entries:
            return None
        entry = self.entries.pop()
        return entry.pre_state

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]

    @staticmethod
    def from_list(items: list[dict[str, Any]]) -> "SessionLog":
        return SessionLog(entries=[LogEntry.from_dict(item) for item in items])
