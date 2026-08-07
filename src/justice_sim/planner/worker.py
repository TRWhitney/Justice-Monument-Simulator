"""Process worker for running CPU-bound planner recommendations."""

from __future__ import annotations

from multiprocessing.connection import Connection
import time

from justice_sim.models.offer import OfferSpec
from justice_sim.models.state import GameState
from justice_sim.planner.rollout import RolloutPlanner


def run_planner_worker(
    planner: RolloutPlanner,
    state: GameState,
    offer: OfferSpec,
    connection: Connection,
) -> None:
    """Run one recommendation and stream coarse progress to the parent process."""
    pending_progress = 0
    last_progress_at = time.monotonic()

    def flush_progress() -> None:
        nonlocal pending_progress, last_progress_at
        if pending_progress:
            connection.send(("progress", pending_progress))
            pending_progress = 0
            last_progress_at = time.monotonic()

    def progress(delta: int) -> None:
        nonlocal pending_progress
        pending_progress += delta
        if time.monotonic() - last_progress_at >= 0.05:
            flush_progress()

    try:
        recommendation = planner.recommend(state, offer, progress=progress)
        flush_progress()
        connection.send(("result", recommendation))
    except (BrokenPipeError, EOFError, OSError):
        # The parent cancelled or closed while calculation was in progress.
        return
    except Exception as exc:  # pragma: no cover - defensive process boundary
        try:
            connection.send(("error", f"{type(exc).__name__}: {exc}"))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()
