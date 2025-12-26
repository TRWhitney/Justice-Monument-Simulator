"""Interactive Rich CLI for Justice Simulator."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import prompt
from rich.console import Console

from justice_sim.config import load_builtin_data
from justice_sim.engine.reducer import ActionNotAllowed, apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.state import GameState
from justice_sim.persistence.logs import SessionLog
from justice_sim.persistence.profiles import Profile, load_profile, save_profile
from justice_sim.persistence.runs import RunState, load_run_state, save_run_state
from justice_sim.engine.scoring import weights_for_preset
from justice_sim.planner.rollout import PlannerConfig, RolloutPlanner
from justice_sim.ui_cli.render import (
    render_recommendation,
    render_search_results,
    render_state,
)
from justice_sim.ui_cli.search import search


class RunSession:
    def __init__(self, data):
        self.data = data
        self.state = GameState(
            case_index=1,
            coins=0,
            pop=0,
            mh=3,
            dismissals=0,
            retirement_chests=0,
        )
        self.rng = Rng()
        self.log = SessionLog()

    def apply(self, offer, action: str) -> None:
        pre_state = self.state
        new_state, random_label = apply_action(
            self.state, offer, action, self.data, self.rng
        )
        self.log.record(
            pre_state, offer.id, action, self.rng.state(), new_state, random_label
        )
        self.state = new_state

    def undo(self) -> None:
        previous = self.log.undo()
        if previous is not None:
            self.state = previous
            if self.log.entries:
                last_rng = self.log.entries[-1].rng_state
                self.rng = Rng.from_state(last_rng)
            else:
                self.rng = Rng(self.rng.seed)


def main() -> int:
    console = Console()
    data = load_builtin_data()
    planner = RolloutPlanner.from_defaults(data)
    session = RunSession(data)

    console.print("Justice Monument Simulator (CLI)")
    while True:
        try:
            render_state(console, session.state)
            query = prompt("Search offer (#npc/$term or command)> ").strip()
        except KeyboardInterrupt:
            console.print("\nExiting.")
            break
        if not query:
            continue
        if query in {"quit", "exit"}:
            break
        if query == "undo":
            session.undo()
            continue
        if query.startswith("export "):
            path = Path(query.split(" ", 1)[1]).expanduser()
            run_state = RunState(
                version="run_state_v1",
                state=session.state,
                rng_state=session.rng.state(),
                log=session.log.to_list(),
            )
            save_run_state(path, run_state)
            console.print(f"Exported run state to {path}")
            continue
        if query.startswith("import "):
            path = Path(query.split(" ", 1)[1]).expanduser()
            loaded = load_run_state(path)
            session.state = loaded.state
            session.rng = Rng.from_state(loaded.rng_state)
            session.log = SessionLog.from_list(loaded.log)
            console.print(f"Imported run state from {path}")
            continue
        if query.startswith("save-profile "):
            path = Path(query.split(" ", 1)[1]).expanduser()
            profile = Profile(
                version="profile_v1", planner_settings=planner.config.__dict__
            )
            save_profile(path, profile)
            console.print(f"Saved profile to {path}")
            continue
        if query.startswith("load-profile "):
            path = Path(query.split(" ", 1)[1]).expanduser()
            profile = load_profile(path)
            if profile.planner_settings:
                planner.config = PlannerConfig(**profile.planner_settings)
                planner.weights = weights_for_preset(planner.config.risk_preset)
            console.print(f"Loaded profile from {path}")
            continue

        results = search(query, data, session.state)
        if not results:
            console.print("No matches.")
            continue
        render_search_results(console, results)
        try:
            selection = prompt("Select offer #> ").strip()
        except KeyboardInterrupt:
            console.print("\nExiting.")
            break
        if not selection.isdigit():
            continue
        index = int(selection) - 1
        if index < 0 or index >= len(results):
            continue
        selected = results[index].offer

        recommendation = planner.recommend(session.state, selected)
        render_recommendation(console, recommendation)

        try:
            action_input = prompt("Action [a/r/d/best/undo/quit]> ").strip().lower()
        except KeyboardInterrupt:
            console.print("\nExiting.")
            break
        if action_input in {"quit", "exit"}:
            break
        if action_input == "undo":
            session.undo()
            continue
        if action_input == "best":
            action = recommendation.best_action
        else:
            mapping = {"a": "approve", "r": "reject", "d": "dismiss"}
            action = mapping.get(action_input, action_input)
        try:
            session.apply(selected, action)
        except ActionNotAllowed as exc:
            console.print(f"Action failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
