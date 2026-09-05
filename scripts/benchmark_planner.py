"""Repeatable engine timings with synthetic state and deterministic score hashes."""

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import platform
from time import perf_counter

from justice_sim.config import load_builtin_data, load_builtin_suggested_rules
from justice_sim.engine.reducer import apply_action
from justice_sim.engine.rng import Rng
from justice_sim.models.offer import EffectSpec, JusticeData
from justice_sim.models.state import EncounterOverride, GameState, ScheduledEvent
from justice_sim.planner.rollout import RolloutPlanner
from justice_sim.util.immutable import thaw_payload


SCENARIOS = ("baseline", "low-health", "loan", "due-event", "override")


def benchmark_state(data: JusticeData, scenario: str) -> GameState:
    state = GameState(11, 50, 20, 8, 2, 0)
    if scenario == "low-health":
        return replace(state, mh=1)
    if scenario == "loan":
        offer = next(o for o in data.offers if o.title == "Scripticus: Kitchen Loan")
        return apply_action(state, offer, "approve", data, Rng(42))[0]
    if scenario == "due-event":
        return replace(
            state,
            scheduled_events=(
                ScheduledEvent(
                    16,
                    (
                        EffectSpec("add_resource", {"resource": "mh", "amount": -2}),
                        EffectSpec(
                            "add_resource", {"resource": "coins", "amount": -15}
                        ),
                    ),
                    label="benchmark_bill",
                ),
            ),
        )
    if scenario == "override":
        return replace(
            state,
            encounter_overrides=(
                EncounterOverride(remaining_uses=3, label="chest_magnetizer"),
            ),
        )
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizons", type=int, nargs="+", default=[12, 20])
    parser.add_argument("--rollouts", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--offer", default="Scripticus: Kitchen Loan")
    parser.add_argument("--no-adaptive", action="store_true")
    parser.add_argument(
        "--scenarios", nargs="+", choices=SCENARIOS, default=["baseline"]
    )
    parser.add_argument(
        "--output", type=Path, help="Explicit optional JSON artifact path"
    )
    args = parser.parse_args()
    if args.rollouts < 1 or any(h < 1 for h in args.horizons):
        parser.error("Horizons and rollout count must be positive")
    data = load_builtin_data()
    rules = load_builtin_suggested_rules(data)
    offer = next((o for o in data.offers if o.title == args.offer), None)
    if offer is None:
        parser.error(f"Unknown offer title: {args.offer}")
    results = []
    for scenario, horizon in ((s, h) for s in args.scenarios for h in args.horizons):
        state = benchmark_state(data, scenario)
        planner = RolloutPlanner.from_defaults(data, rules, seed=args.seed)
        planner.config = replace(
            planner.config,
            horizon_cases=horizon,
            rollouts_per_action=args.rollouts,
            adaptive_rollouts=not args.no_adaptive,
        )
        start = perf_counter()
        recommendation = planner.recommend(state, offer)
        seconds = perf_counter() - start
        scores = json.dumps(asdict(recommendation), sort_keys=True).encode()
        result = {
            "scenario": scenario,
            "python": platform.python_version(),
            "offer": offer.title,
            "state": thaw_payload(asdict(state)),
            "seed": args.seed,
            "config": asdict(planner.config),
            "seconds": seconds,
            "samples": {s.action: s.sample_count for s in recommendation.action_scores},
            "best_action": recommendation.best_action,
            "score_sha256": hashlib.sha256(scores).hexdigest(),
        }
        # The synthetic state's empty flags need a JSON representation.
        result["state"]["flags"] = sorted(state.flags)
        results.append(result)
        print(json.dumps(result), flush=True)
    if args.output:
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
