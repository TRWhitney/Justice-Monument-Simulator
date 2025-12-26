"""Asset path helpers."""

from __future__ import annotations

from pathlib import Path

from justice_sim.models.offer import JusticeData, NpcSpec


def resolve_npc_image_path(data: JusticeData, npc: NpcSpec) -> Path | None:
    if not npc.image:
        return None
    repo_root = Path(__file__).resolve().parents[3]
    data_root = repo_root / "src" / "justice_sim" / "data"
    return data_root / npc.image
