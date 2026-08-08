#!/usr/bin/env python3
"""Analyze saved Justice Monument runs without changing simulator behavior."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from justice_sim.analysis.encounter_selection import (
    DEFAULT_RESAMPLES,
    DEFAULT_SEED,
    RunParseError,
    analyze_runs,
    data_sha256,
    deduplicate_runs,
    load_history,
    parse_run,
    record_snapshot,
    write_history,
    write_report,
)
from justice_sim.config import BUILTIN_DATA_PATH, REPO_ROOT, load_data


DEFAULT_HISTORY_PATH = REPO_ROOT / "analysis" / "encounter-selection-history.json"
DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "encounter-selection-analysis.html"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze encounter frequency and ordering in saved run JSON files."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        default=[REPO_ROOT / "scratch"],
        help="Run files or directories to scan recursively (default: scratch)",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=BUILTIN_DATA_PATH,
        help="Justice data JSON used for offer mapping and eligibility",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    parser.add_argument(
        "--record",
        action="store_true",
        help="Append a deduplicated aggregate snapshot and regenerate the HTML report",
    )
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def _discover(inputs: list[Path]) -> tuple[list[tuple[Path, bool]], list[str]]:
    files: list[tuple[Path, bool]] = []
    errors: list[str] = []
    for path in inputs:
        resolved = path if path.is_absolute() else REPO_ROOT / path
        if resolved.is_file():
            files.append((resolved, True))
        elif resolved.is_dir():
            files.extend(
                (candidate, False)
                for candidate in sorted(resolved.rglob("*"))
                if candidate.is_file() and not candidate.name.startswith(".")
            )
        else:
            errors.append(f"Input does not exist: {path}")
    return files, errors


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.resamples < 1:
        print("--resamples must be positive", file=sys.stderr)
        return 2
    try:
        data = load_data(args.data)
    except Exception as exc:  # noqa: BLE001 - CLI boundary adds useful context
        print(f"Could not load Justice data: {exc}", file=sys.stderr)
        return 2

    discovered, discovery_errors = _discover(args.inputs)
    if discovery_errors:
        print("\n".join(discovery_errors), file=sys.stderr)
        return 2
    parsed = []
    skipped: list[str] = []
    for path, explicit in discovered:
        try:
            parsed.append(parse_run(path, data))
        except RunParseError as exc:
            if explicit:
                print(str(exc), file=sys.stderr)
                return 2
            skipped.append(str(exc))
    runs, duplicates = deduplicate_runs(parsed)
    if not runs:
        print("No valid saved runs were found.", file=sys.stderr)
        for item in skipped:
            print(f"Skipped: {item}", file=sys.stderr)
        return 2

    snapshot = analyze_runs(
        runs,
        data,
        data_hash=data_sha256(args.data),
        resamples=args.resamples,
        seed=args.seed,
    )
    counts = snapshot["counts"]
    print(
        f"Analyzed {counts['runs']} runs: {counts['encounters']} encounters, "
        f"{counts['ordinary']} ordinary, "
        f"{counts['manual_adjustments']} manual adjustments."
    )
    for conclusion in snapshot["conclusions"]:
        adjusted = conclusion.get("adjusted_p_value")
        p_text = "n/a" if adjusted is None else f"{adjusted:.5f}"
        print(
            f"- {conclusion['name']}: {conclusion['evidence']} "
            f"({conclusion['direction']}, adjusted p={p_text})"
        )
    for item in duplicates:
        print(f"Duplicate content ignored: {item}", file=sys.stderr)
    for item in skipped:
        print(f"Skipped discovered file: {item}", file=sys.stderr)

    if args.record:
        history_path = (
            args.history if args.history.is_absolute() else REPO_ROOT / args.history
        )
        report_path = (
            args.report if args.report.is_absolute() else REPO_ROOT / args.report
        )
        history = record_snapshot(load_history(history_path), snapshot)
        write_history(history_path, history)
        write_report(report_path, history)
        print(f"Recorded aggregate history: {history_path}")
        print(f"Generated report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
