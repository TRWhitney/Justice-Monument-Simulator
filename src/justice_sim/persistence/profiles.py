"""Profile save/load helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Profile:
    version: str
    progression: Mapping[str, Any] = field(default_factory=dict)
    planner_settings: Mapping[str, Any] = field(default_factory=dict)
    encounter_model: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "progression": dict(self.progression),
            "planner_settings": dict(self.planner_settings),
            "encounter_model": dict(self.encounter_model),
        }

    @staticmethod
    def from_dict(payload: Mapping[str, Any]) -> "Profile":
        return Profile(
            version=str(payload.get("version", "profile_v1")),
            progression=payload.get("progression", {}),
            planner_settings=payload.get("planner_settings", {}),
            encounter_model=payload.get("encounter_model", {}),
        )


def save_profile(path: Path, profile: Profile) -> None:
    path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")


def load_profile(path: Path) -> Profile:
    return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))
