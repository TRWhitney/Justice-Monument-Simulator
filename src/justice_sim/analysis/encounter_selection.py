"""Repeatable analysis of observed encounter sequences.

The analysis deliberately separates order-only evidence from evidence that depends on
the simulator's current eligibility model.  Saved resource values are used only for
the latter sensitivity analysis.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence

from justice_sim.engine.encounter import UniformEncounterModel
from justice_sim.models.offer import JusticeData
from justice_sim.persistence.runs import deserialize_state


ANALYSIS_VERSION = "encounter_selection_v1"
HISTORY_VERSION = "encounter_selection_history_v1"
DEFAULT_RESAMPLES = 100_000
DEFAULT_SEED = 0


class RunParseError(ValueError):
    """Raised when an explicitly selected file is not a usable saved run."""


@dataclass(frozen=True)
class Observation:
    run_id: str
    segment: int
    case_index: int
    offer_id: str
    npc_id: str
    action: str
    pre_state: Mapping[str, Any]
    exclusion_reason: str | None
    eligible_reconstructed: tuple[str, ...]
    eligible_all_offers: tuple[str, ...]

    @property
    def is_ordinary(self) -> bool:
        return self.exclusion_reason is None


@dataclass(frozen=True)
class ParsedRun:
    run_id: str
    source_hash: str
    log_entries: int
    manual_adjustments: int
    observations: tuple[Observation, ...]
    segment_count: int
    warnings: tuple[str, ...] = ()

    @property
    def ordinary(self) -> tuple[Observation, ...]:
        return tuple(item for item in self.observations if item.is_ordinary)


@dataclass
class _NullSamples:
    observed: float
    values: list[float] = field(default_factory=list)
    tail: str = "high"

    def result(self, name: str) -> dict[str, Any]:
        null_mean = fmean(self.values) if self.values else 0.0
        if self.tail == "two-sided":
            distance = abs(self.observed - null_mean)
            extreme = sum(abs(value - null_mean) >= distance for value in self.values)
        elif self.tail == "low":
            extreme = sum(value <= self.observed for value in self.values)
        else:
            extreme = sum(value >= self.observed for value in self.values)
        p_value = (extreme + 1) / (len(self.values) + 1)
        direction = _direction(self.observed, null_mean)
        return {
            "name": name,
            "observed": self.observed,
            "null_mean": null_mean,
            "null_interval": [
                _percentile(self.values, 0.025),
                _percentile(self.values, 0.975),
            ],
            "p_value": p_value,
            "direction": direction,
            "tail": self.tail,
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def data_sha256(data_path: Path) -> str:
    return file_sha256(data_path)


def parse_run(path: Path, data: JusticeData) -> ParsedRun:
    """Parse one saved run without retaining its path or resource values in results."""
    source_hash = file_sha256(path)
    run_id = f"run-{source_hash[:10]}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunParseError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != "run_state_v1":
        raise RunParseError(f"{path}: expected a run_state_v1 JSON object")
    log = payload.get("log")
    if not isinstance(log, list):
        raise RunParseError(f"{path}: log must be a list")

    all_regular = _all_regular_offer_ids(data)
    model = UniformEncounterModel()
    warnings: list[str] = []
    observations: list[Observation] = []
    manual_adjustments = 0
    segment = 1
    previous_case: int | None = None

    for log_index, raw in enumerate(log):
        if not isinstance(raw, dict):
            warnings.append(
                f"log entry {log_index + 1} is not an object and was skipped"
            )
            continue
        if raw.get("action") == "adjust" or raw.get("offer_id") == "manual_adjust":
            manual_adjustments += 1
            continue
        pre_state = raw.get("pre_state")
        offer_id = raw.get("offer_id")
        if not isinstance(pre_state, dict) or not isinstance(offer_id, str):
            warnings.append(
                f"log entry {log_index + 1} lacks pre_state or offer_id and was skipped"
            )
            continue
        try:
            case_index = int(pre_state["case_index"])
        except (KeyError, TypeError, ValueError):
            warnings.append(f"log entry {log_index + 1} has no valid case index")
            continue
        if previous_case is not None and case_index != previous_case + 1:
            segment += 1
            warnings.append(
                f"sequence discontinuity before case {case_index}; started segment {segment}"
            )
        previous_case = case_index

        offer = data.offers_by_id.get(offer_id)
        npc_id = offer.npc_id if offer else f"unknown:{offer_id}"
        if offer is None:
            warnings.append(f"case {case_index} has unknown offer {offer_id!r}")

        reconstructed: tuple[str, ...] = ()
        try:
            state = deserialize_state(pre_state)
            reconstructed = tuple(model.eligible_offers(state, data))
        except (KeyError, TypeError, ValueError) as exc:
            warnings.append(
                f"case {case_index} eligibility could not be reconstructed: {exc}"
            )

        observations.append(
            Observation(
                run_id=run_id,
                segment=segment,
                case_index=case_index,
                offer_id=offer_id,
                npc_id=npc_id,
                action=str(raw.get("action", "")),
                pre_state=pre_state,
                exclusion_reason=_exclusion_reason(
                    case_index, offer_id, pre_state, data
                ),
                eligible_reconstructed=reconstructed,
                eligible_all_offers=all_regular,
            )
        )

    if not observations:
        raise RunParseError(f"{path}: no encounter observations were found")
    return ParsedRun(
        run_id=run_id,
        source_hash=source_hash,
        log_entries=len(log),
        manual_adjustments=manual_adjustments,
        observations=tuple(observations),
        segment_count=segment,
        warnings=tuple(warnings),
    )


def _all_regular_offer_ids(data: JusticeData) -> tuple[str, ...]:
    excluded = set(data.special_rules.harbinger.offer_pool)
    excluded.add(data.special_rules.harbinger.offer_id)
    if data.special_rules.gratefulbinger:
        excluded.add(data.special_rules.gratefulbinger.offer_id)
    return tuple(offer.id for offer in data.offers if offer.id not in excluded)


def _exclusion_reason(
    case_index: int,
    offer_id: str,
    pre_state: Mapping[str, Any],
    data: JusticeData,
) -> str | None:
    cadence = data.special_rules.harbinger.cadence_modulus
    harbinger_ids = set(data.special_rules.harbinger.offer_pool)
    harbinger_ids.add(data.special_rules.harbinger.offer_id)
    if data.special_rules.gratefulbinger:
        harbinger_ids.add(data.special_rules.gratefulbinger.offer_id)
    if case_index % cadence == 0:
        return "cadence"
    if offer_id in harbinger_ids:
        return "special_off_cadence"
    for forced in pre_state.get("forced_encounters", []) or []:
        if isinstance(forced, dict) and forced.get("trigger_case_index") == case_index:
            return "forced"
    if pre_state.get("encounter_overrides"):
        return "override_possible"
    return None


def deduplicate_runs(runs: Iterable[ParsedRun]) -> tuple[list[ParsedRun], list[str]]:
    unique: list[ParsedRun] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for run in runs:
        if run.source_hash in seen:
            duplicates.append(run.run_id)
            continue
        seen.add(run.source_hash)
        unique.append(run)
    return unique, duplicates


def analyze_runs(
    runs: Sequence[ParsedRun],
    data: JusticeData,
    *,
    data_hash: str,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    if not runs:
        raise ValueError("At least one parsed run is required")
    if resamples < 1:
        raise ValueError("resamples must be positive")

    ordinary = [item for run in runs for item in run.ordinary]
    all_observations = [item for run in runs for item in run.observations]
    frequency_reconstructed = _frequency_analysis(
        ordinary,
        data,
        candidate_attribute="eligible_reconstructed",
        resamples=resamples,
        seed=seed + 101,
    )
    frequency_all = _frequency_analysis(
        ordinary,
        data,
        candidate_attribute="eligible_all_offers",
        resamples=resamples,
        seed=seed + 202,
    )
    order = _order_analysis(runs, resamples=resamples, seed=seed + 303)

    primary = [
        frequency_reconstructed["npc_test"],
        frequency_reconstructed["offer_test"],
        *order["tests"],
    ]
    leave_one_out_consistency = _leave_one_out_consistency(
        runs,
        data,
        primary,
        resamples=resamples,
        seed=seed + 404,
    )
    adjusted = holm_adjust([float(test["p_value"]) for test in primary])
    for test, adjusted_p in zip(primary, adjusted, strict=True):
        test["adjusted_p_value"] = adjusted_p
        test["leave_one_run_out_consistent"] = leave_one_out_consistency.get(
            test["name"], False
        )
        test["evidence"] = evidence_label(
            adjusted_p,
            len(runs),
            leave_one_run_out_consistent=test["leave_one_run_out_consistent"],
        )

    sensitivity_by_name = {
        frequency_all["npc_test"]["name"]: frequency_all["npc_test"],
        frequency_all["offer_test"]["name"]: frequency_all["offer_test"],
    }
    for primary_test in (
        frequency_reconstructed["npc_test"],
        frequency_reconstructed["offer_test"],
    ):
        sensitivity = sensitivity_by_name[primary_test["name"]]
        sensitive = (primary_test["p_value"] <= 0.05) != (
            sensitivity["p_value"] <= 0.05
        )
        primary_test["model_sensitive"] = sensitive
        if sensitive:
            primary_test["evidence"] = "model-sensitive"

    fingerprint_payload = {
        "analysis_version": ANALYSIS_VERSION,
        "data_hash": data_hash,
        "resamples": resamples,
        "seed": seed,
        "sources": sorted(run.source_hash for run in runs),
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    exclusions = Counter(
        item.exclusion_reason for item in all_observations if item.exclusion_reason
    )
    return {
        "analysis_version": ANALYSIS_VERSION,
        "fingerprint": fingerprint,
        "data_hash": data_hash,
        "seed": seed,
        "resamples": resamples,
        "source_hashes": sorted(run.source_hash for run in runs),
        "counts": {
            "runs": len(runs),
            "log_entries": sum(run.log_entries for run in runs),
            "encounters": len(all_observations),
            "ordinary": len(ordinary),
            "manual_adjustments": sum(run.manual_adjustments for run in runs),
            "excluded": dict(sorted(exclusions.items())),
            "segments": sum(run.segment_count for run in runs),
        },
        "warnings": [warning for run in runs for warning in run.warnings],
        "runs": [_run_summary(run) for run in runs],
        "frequency": {
            "reconstructed": frequency_reconstructed,
            "all_offers_sensitivity": frequency_all,
        },
        "order": order,
        "top_transitions": _top_transitions(runs),
        "conclusions": _conclusions(primary),
    }


def _run_summary(run: ParsedRun) -> dict[str, Any]:
    ordinary = list(run.ordinary)
    return {
        "run_id": run.run_id,
        "source_hash": run.source_hash,
        "log_entries": run.log_entries,
        "encounters": len(run.observations),
        "ordinary": len(ordinary),
        "manual_adjustments": run.manual_adjustments,
        "segments": run.segment_count,
        "warnings": list(run.warnings),
        "npc_counts": dict(sorted(Counter(item.npc_id for item in ordinary).items())),
        "npc_repeats": _immediate_repeats([item.npc_id for item in ordinary]),
        "offer_repeats": _immediate_repeats([item.offer_id for item in ordinary]),
    }


def _frequency_analysis(
    observations: Sequence[Observation],
    data: JusticeData,
    *,
    candidate_attribute: str,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    usable: list[tuple[Observation, tuple[str, ...]]] = []
    incompatible: list[Observation] = []
    for item in observations:
        candidates = tuple(getattr(item, candidate_attribute))
        if not candidates or item.offer_id not in candidates:
            incompatible.append(item)
            continue
        usable.append((item, candidates))

    observed_offers = Counter(item.offer_id for item, _ in usable)
    observed_npcs = Counter(item.npc_id for item, _ in usable)
    expected_offers: Counter[str] = Counter()
    expected_npcs: Counter[str] = Counter()
    for _, candidates in usable:
        probability = 1.0 / len(candidates)
        for offer_id in candidates:
            expected_offers[offer_id] += probability
            offer = data.offers_by_id.get(offer_id)
            if offer:
                expected_npcs[offer.npc_id] += probability

    observed_npc_stat = _pearson_stat(observed_npcs, expected_npcs)
    observed_offer_stat = _pearson_stat(observed_offers, expected_offers)
    npc_samples = _NullSamples(observed_npc_stat)
    offer_samples = _NullSamples(observed_offer_stat)
    rng = random.Random(seed)
    for _ in range(resamples):
        simulated_offers: Counter[str] = Counter()
        simulated_npcs: Counter[str] = Counter()
        for _, candidates in usable:
            chosen = candidates[rng.randrange(len(candidates))]
            simulated_offers[chosen] += 1
            offer = data.offers_by_id.get(chosen)
            if offer:
                simulated_npcs[offer.npc_id] += 1
        npc_samples.values.append(_pearson_stat(simulated_npcs, expected_npcs))
        offer_samples.values.append(_pearson_stat(simulated_offers, expected_offers))

    npc_test = npc_samples.result("NPC frequency vs uniform eligible offers")
    offer_test = offer_samples.result("Offer frequency vs uniform eligible offers")
    residuals = []
    for npc_id in sorted(expected_npcs):
        expected = expected_npcs[npc_id]
        observed = observed_npcs[npc_id]
        variance = max(expected * (1 - expected / max(len(usable), 1)), 1e-12)
        residuals.append(
            {
                "npc_id": npc_id,
                "observed": observed,
                "expected": expected,
                "ratio": observed / expected if expected else None,
                "standardized_residual": (observed - expected) / math.sqrt(variance),
            }
        )
    residuals.sort(key=lambda item: abs(item["standardized_residual"]), reverse=True)
    offer_residuals = []
    for offer_id in sorted(expected_offers):
        expected = expected_offers[offer_id]
        observed = observed_offers[offer_id]
        variance = max(expected * (1 - expected / max(len(usable), 1)), 1e-12)
        offer = data.offers_by_id.get(offer_id)
        offer_residuals.append(
            {
                "offer_id": offer_id,
                "title": offer.title if offer else offer_id,
                "npc_id": offer.npc_id if offer else "unknown",
                "observed": observed,
                "expected": expected,
                "ratio": observed / expected if expected else None,
                "standardized_residual": (observed - expected) / math.sqrt(variance),
            }
        )
    offer_residuals.sort(
        key=lambda item: abs(item["standardized_residual"]), reverse=True
    )

    uniform_offer_ll = 0.0
    uniform_npc_ll = 0.0
    for item, candidates in usable:
        uniform_offer_ll -= math.log(len(candidates))
        by_npc: dict[str, list[str]] = defaultdict(list)
        for offer_id in candidates:
            offer = data.offers_by_id.get(offer_id)
            if offer:
                by_npc[offer.npc_id].append(offer_id)
        npc_candidates = by_npc.get(item.npc_id, [])
        if npc_candidates:
            uniform_npc_ll -= math.log(len(by_npc)) + math.log(len(npc_candidates))
    delta_bits = (
        (uniform_npc_ll - uniform_offer_ll) / (len(usable) * math.log(2))
        if usable
        else 0.0
    )
    return {
        "candidate_model": candidate_attribute,
        "usable": len(usable),
        "incompatible": len(incompatible),
        "incompatible_cases": [
            {"run_id": item.run_id, "case_index": item.case_index}
            for item in incompatible
        ],
        "npc_test": npc_test,
        "offer_test": offer_test,
        "uniform_npc_minus_offer_bits_per_encounter": delta_bits,
        "top_npc_residuals": residuals[:10],
        "top_offer_residuals": offer_residuals[:15],
    }


def _leave_one_out_consistency(
    runs: Sequence[ParsedRun],
    data: JusticeData,
    pooled_tests: Sequence[Mapping[str, Any]],
    *,
    resamples: int,
    seed: int,
) -> dict[str, bool]:
    """Check whether every leave-one-run-out effect has the pooled direction."""
    if len(runs) < 3:
        return {}
    validation_resamples = min(999, max(99, resamples // 100))
    directions: dict[str, list[str]] = defaultdict(list)
    for omitted_index in range(len(runs)):
        remaining = [run for index, run in enumerate(runs) if index != omitted_index]
        ordinary = [item for run in remaining for item in run.ordinary]
        frequency = _frequency_analysis(
            ordinary,
            data,
            candidate_attribute="eligible_reconstructed",
            resamples=validation_resamples,
            seed=seed + omitted_index * 17,
        )
        order = _order_analysis(
            remaining,
            resamples=validation_resamples,
            seed=seed + omitted_index * 17 + 1,
        )
        for test in (frequency["npc_test"], frequency["offer_test"], *order["tests"]):
            directions[test["name"]].append(test["direction"])
    return {
        test["name"]: bool(directions[test["name"]])
        and test["direction"] != "similar"
        and all(
            direction == test["direction"] for direction in directions[test["name"]]
        )
        for test in pooled_tests
    }


def _pearson_stat(observed: Mapping[str, int], expected: Mapping[str, float]) -> float:
    return sum(
        ((observed.get(category, 0) - expected_count) ** 2) / expected_count
        for category, expected_count in expected.items()
        if expected_count > 0
    )


def _order_analysis(
    runs: Sequence[ParsedRun], *, resamples: int, seed: int
) -> dict[str, Any]:
    sequences = _ordinary_sequences(runs)
    observed = _sequence_statistics(sequences)
    samples = {
        "Immediate NPC repeats": _NullSamples(
            observed["npc_repeats"], tail="two-sided"
        ),
        "Immediate exact-offer repeats": _NullSamples(
            observed["offer_repeats"], tail="two-sided"
        ),
        "Longest NPC streak": _NullSamples(
            observed["longest_npc_streak"], tail="two-sided"
        ),
        "Five-draw NPC diversity": _NullSamples(
            observed["window_diversity"], tail="two-sided"
        ),
        "Lag-one NPC mutual information": _NullSamples(observed["lag_one_mi"]),
        "Maximum NPC mutual information, lags 1-5": _NullSamples(
            observed["max_lag_mi"]
        ),
        "Within-NPC exact-offer repeats": _NullSamples(
            observed["within_npc_offer_repeats"], tail="two-sided"
        ),
        "NPC dependence on cadence slot": _NullSamples(observed["cadence_mi"]),
        "Categorical change-point scan": _NullSamples(observed["change_point"]),
    }
    run_heterogeneity = _NullSamples(observed["run_mi"])
    rng = random.Random(seed)
    for _ in range(resamples):
        permuted = []
        for sequence in sequences:
            labels = [(item[1], item[2]) for item in sequence]
            rng.shuffle(labels)
            permuted.append(
                [
                    (case_index, npc_id, offer_id, run_id)
                    for (case_index, _, _, run_id), (npc_id, offer_id) in zip(
                        sequence, labels, strict=True
                    )
                ]
            )
        values = _sequence_statistics(permuted)
        for name, key in (
            ("Immediate NPC repeats", "npc_repeats"),
            ("Immediate exact-offer repeats", "offer_repeats"),
            ("Longest NPC streak", "longest_npc_streak"),
            ("Five-draw NPC diversity", "window_diversity"),
            ("Lag-one NPC mutual information", "lag_one_mi"),
            ("Maximum NPC mutual information, lags 1-5", "max_lag_mi"),
            ("Within-NPC exact-offer repeats", "within_npc_offer_repeats"),
            ("NPC dependence on cadence slot", "cadence_mi"),
            ("Categorical change-point scan", "change_point"),
        ):
            samples[name].values.append(values[key])

        global_labels = [
            (item[1], item[2]) for sequence in sequences for item in sequence
        ]
        rng.shuffle(global_labels)
        offset = 0
        heterogeneity_permutation = []
        for sequence in sequences:
            current = global_labels[offset : offset + len(sequence)]
            offset += len(sequence)
            heterogeneity_permutation.append(
                [
                    (case_index, npc_id, offer_id, run_id)
                    for (case_index, _, _, run_id), (npc_id, offer_id) in zip(
                        sequence, current, strict=True
                    )
                ]
            )
        heterogeneity_values = _sequence_statistics(heterogeneity_permutation)
        run_heterogeneity.values.append(heterogeneity_values["run_mi"])

    tests = [sample.result(name) for name, sample in samples.items()]
    tests.append(run_heterogeneity.result("NPC distribution differs between runs"))
    return {"tests": tests, "observed": observed}


def _ordinary_sequences(
    runs: Sequence[ParsedRun],
) -> list[list[tuple[int, str, str, str]]]:
    grouped: dict[tuple[str, int], list[tuple[int, str, str, str]]] = defaultdict(list)
    for run in runs:
        for item in run.ordinary:
            grouped[(run.run_id, item.segment)].append(
                (item.case_index, item.npc_id, item.offer_id, run.run_id)
            )
    return [grouped[key] for key in sorted(grouped)]


def _sequence_statistics(
    sequences: Sequence[Sequence[tuple[int, str, str, str]]],
) -> dict[str, float]:
    npc_sequences = [[item[1] for item in sequence] for sequence in sequences]
    offer_sequences = [[item[2] for item in sequence] for sequence in sequences]
    npc_repeats = sum(_immediate_repeats(sequence) for sequence in npc_sequences)
    offer_repeats = sum(_immediate_repeats(sequence) for sequence in offer_sequences)
    longest = max((_longest_streak(sequence) for sequence in npc_sequences), default=0)
    windows = [
        len(set(sequence[index : index + 5]))
        for sequence in npc_sequences
        for index in range(max(0, len(sequence) - 4))
    ]
    window_diversity = fmean(windows) if windows else 0.0
    lag_values = [_lag_mutual_information(npc_sequences, lag) for lag in range(1, 6)]

    within_npc_repeats = 0
    for sequence in sequences:
        by_npc: dict[str, list[str]] = defaultdict(list)
        for _, npc_id, offer_id, _ in sequence:
            by_npc[npc_id].append(offer_id)
        within_npc_repeats += sum(
            _immediate_repeats(offers) for offers in by_npc.values()
        )

    cadence_pairs = [
        (item[1], str(item[0] % 5)) for sequence in sequences for item in sequence
    ]
    run_pairs = [(item[1], item[3]) for sequence in sequences for item in sequence]
    return {
        "npc_repeats": float(npc_repeats),
        "offer_repeats": float(offer_repeats),
        "longest_npc_streak": float(longest),
        "window_diversity": window_diversity,
        "lag_one_mi": lag_values[0],
        "max_lag_mi": max(lag_values, default=0.0),
        "within_npc_offer_repeats": float(within_npc_repeats),
        "cadence_mi": _mutual_information(cadence_pairs),
        "run_mi": _mutual_information(run_pairs),
        "change_point": max(
            (_change_point_stat(sequence) for sequence in npc_sequences), default=0.0
        ),
    }


def _immediate_repeats(sequence: Sequence[str]) -> int:
    return sum(left == right for left, right in zip(sequence, sequence[1:]))


def _longest_streak(sequence: Sequence[str]) -> int:
    if not sequence:
        return 0
    best = current = 1
    for left, right in zip(sequence, sequence[1:]):
        current = current + 1 if left == right else 1
        best = max(best, current)
    return best


def _lag_mutual_information(sequences: Sequence[Sequence[str]], lag: int) -> float:
    pairs = [
        (sequence[index], sequence[index + lag])
        for sequence in sequences
        for index in range(max(0, len(sequence) - lag))
    ]
    return _mutual_information(pairs)


def _mutual_information(pairs: Sequence[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    joint = Counter(pairs)
    left = Counter(item[0] for item in pairs)
    right = Counter(item[1] for item in pairs)
    total = len(pairs)
    return sum(
        (count / total)
        * math.log2((count * total) / (left[left_value] * right[right_value]))
        for (left_value, right_value), count in joint.items()
    )


def _change_point_stat(sequence: Sequence[str], minimum_side: int = 10) -> float:
    if len(sequence) < minimum_side * 2:
        return 0.0
    best = 0.0
    for split in range(minimum_side, len(sequence) - minimum_side + 1):
        pairs = [(value, "before") for value in sequence[:split]]
        pairs.extend((value, "after") for value in sequence[split:])
        best = max(best, _mutual_information(pairs))
    return best


def _top_transitions(runs: Sequence[ParsedRun]) -> list[dict[str, Any]]:
    transitions: Counter[tuple[str, str]] = Counter()
    for sequence in _ordinary_sequences(runs):
        npcs = [item[1] for item in sequence]
        transitions.update(zip(npcs, npcs[1:]))
    return [
        {"from": source, "to": target, "count": count}
        for (source, target), count in transitions.most_common(15)
    ]


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Return Holm-adjusted p-values in their original order."""
    count = len(p_values)
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [1.0] * count
    running = 0.0
    for rank, (original_index, p_value) in enumerate(ordered):
        running = max(running, min(1.0, (count - rank) * p_value))
        adjusted[original_index] = running
    return adjusted


def evidence_label(
    adjusted_p_value: float,
    run_count: int,
    *,
    leave_one_run_out_consistent: bool = False,
    model_sensitive: bool = False,
) -> str:
    if model_sensitive:
        return "model-sensitive"
    if adjusted_p_value > 0.05:
        return "not detected"
    if run_count >= 3 and leave_one_run_out_consistent:
        return "repeated"
    return "tentative"


def _conclusions(tests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": test["name"],
            "evidence": test.get("evidence", "not detected"),
            "direction": test["direction"],
            "observed": test["observed"],
            "null_mean": test["null_mean"],
            "adjusted_p_value": test.get("adjusted_p_value"),
        }
        for test in tests
    ]


def _direction(observed: float, expected: float, tolerance: float = 1e-12) -> str:
    if observed > expected + tolerance:
        return "higher"
    if observed < expected - tolerance:
        return "lower"
    return "similar"


def _percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = probability * (len(ordered) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": HISTORY_VERSION, "snapshots": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != HISTORY_VERSION:
        raise ValueError(f"Unsupported encounter analysis history at {path}")
    if not isinstance(payload.get("snapshots"), list):
        raise ValueError(
            f"Encounter analysis history snapshots must be a list at {path}"
        )
    return payload


def record_snapshot(
    history: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    snapshots = [dict(item) for item in history.get("snapshots", [])]
    fingerprint = snapshot["fingerprint"]
    if any(item.get("fingerprint") == fingerprint for item in snapshots):
        return {"version": HISTORY_VERSION, "snapshots": snapshots}
    recorded = dict(snapshot)
    recorded["recorded_at"] = datetime.now(timezone.utc).isoformat()
    snapshots.append(recorded)
    return {"version": HISTORY_VERSION, "snapshots": snapshots}


def write_history(path: Path, history: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def render_report(history: Mapping[str, Any]) -> str:
    snapshots = list(history.get("snapshots", []))
    if not snapshots:
        raise ValueError("Cannot render an encounter report without snapshots")
    current = snapshots[-1]
    counts = current["counts"]
    conclusions = current["conclusions"]
    run_rows = "".join(
        "<tr>"
        f"<td><code>{escape(run['run_id'])}</code></td>"
        f"<td>{run['encounters']}</td><td>{run['ordinary']}</td>"
        f"<td>{run['manual_adjustments']}</td><td>{run['segments']}</td>"
        f"<td>{run['npc_repeats']}</td><td>{run['offer_repeats']}</td>"
        "</tr>"
        for run in current["runs"]
    )
    finding_rows = "".join(
        "<tr>"
        f"<td>{escape(item['name'])}</td>"
        f'<td><span class="status {escape(item["evidence"].replace(" ", "-"))}">'
        f"{escape(item['evidence'])}</span></td>"
        f"<td>{_format_number(item['observed'])}</td>"
        f"<td>{_format_number(item['null_mean'])}</td>"
        f"<td>{escape(item['direction'])}</td>"
        f"<td>{_format_p(item.get('adjusted_p_value'))}</td>"
        "</tr>"
        for item in conclusions
    )
    history_rows = "".join(
        "<tr>"
        f"<td>{escape(item.get('recorded_at', 'unknown'))}</td>"
        f"<td><code>{escape(item['fingerprint'][:12])}</code></td>"
        f"<td>{item['counts']['runs']}</td>"
        f"<td>{item['counts']['ordinary']}</td>"
        f"<td>{sum(c['evidence'] != 'not detected' for c in item['conclusions'])}</td>"
        "</tr>"
        for item in reversed(snapshots)
    )
    transition_rows = "".join(
        "<tr>"
        f"<td>{escape(item['from'])}</td><td>{escape(item['to'])}</td>"
        f"<td>{item['count']}</td></tr>"
        for item in current["top_transitions"]
    )
    npc_totals = Counter()
    for run in current["runs"]:
        npc_totals.update(run["npc_counts"])
    maximum = max(npc_totals.values(), default=1)
    bars = "".join(
        '<div class="bar-row">'
        f"<span>{escape(npc)}</span>"
        f'<div class="bar" style="--width:{count / maximum:.4f}"></div>'
        f"<strong>{count}</strong></div>"
        for npc, count in npc_totals.most_common()
    )
    warnings = current.get("warnings", [])
    warning_html = (
        "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in warnings) + "</ul>"
        if warnings
        else "<p>No parser or sequence-integrity warnings were recorded.</p>"
    )
    reconstructed = current["frequency"]["reconstructed"]
    sensitivity = current["frequency"]["all_offers_sensitivity"]
    top_npc = reconstructed["top_npc_residuals"][0]
    offer_residual_rows = "".join(
        "<tr>"
        f"<td>{escape(item['title'])}</td><td>{escape(item['npc_id'])}</td>"
        f"<td>{item['observed']}</td><td>{item['expected']:.2f}</td>"
        f"<td>{item['ratio']:.2f}×</td>"
        f"<td>{item['standardized_residual']:+.2f}</td></tr>"
        for item in reconstructed["top_offer_residuals"][:10]
    )
    detected = [item for item in conclusions if item["evidence"] != "not detected"]
    if detected:
        detected_text = "; ".join(
            f"{escape(item['name'])} ({escape(item['evidence'])})" for item in detected
        )
    else:
        detected_text = "No primary test crossed the adjusted 0.05 threshold."
    model_comparison = (
        "uniform eligible-offer selection"
        if reconstructed["uniform_npc_minus_offer_bits_per_encounter"] < 0
        else "uniform NPC-first selection"
    )
    evidence_ceiling = (
        f"With {counts['runs']} runs, no result can be classified above tentative."
        if counts["runs"] < 3
        else "Repeated evidence additionally requires consistent leave-one-run-out direction."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Encounter Selection Analysis</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.5; }}
    body {{ margin: 0 auto; max-width: 78rem; padding: 2rem; }}
    h1, h2 {{ line-height: 1.2; }}
    .callout {{ border-left: .35rem solid #4d8ed8; padding: .3rem 1rem; background: color-mix(in srgb, #4d8ed8 9%, transparent); }}
    .warning {{ border-color: #d99728; background: color-mix(in srgb, #d99728 10%, transparent); }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: .8rem; margin: 1rem 0; }}
    .card {{ border: 1px solid color-mix(in srgb, currentColor 22%, transparent); border-radius: .5rem; padding: .8rem; }}
    .card strong {{ display: block; font-size: 1.7rem; }}
    .table-wrap {{ max-width: 100%; overflow-x: auto; margin: 1rem 0 2rem; }}
    table {{ border-collapse: collapse; min-width: 100%; width: max-content; }}
    th, td {{ border: 1px solid color-mix(in srgb, currentColor 24%, transparent); padding: .45rem .65rem; text-align: right; white-space: nowrap; }}
    th:first-child, td:first-child {{ text-align: left; }}
    code {{ background: color-mix(in srgb, currentColor 10%, transparent); border-radius: .2rem; padding: .1rem .25rem; }}
    code.hash {{ overflow-wrap: anywhere; word-break: break-all; }}
    .status {{ border-radius: 999px; padding: .1rem .5rem; background: color-mix(in srgb, currentColor 10%, transparent); }}
    .status.tentative {{ background: color-mix(in srgb, #d99728 25%, transparent); }}
    .status.repeated {{ background: color-mix(in srgb, #29966f 25%, transparent); }}
    .status.model-sensitive {{ background: color-mix(in srgb, #bc5caa 25%, transparent); }}
    .bar-row {{ display: grid; grid-template-columns: minmax(12rem, 1fr) 3fr 3rem; gap: .6rem; align-items: center; margin: .3rem 0; }}
    .bar {{ height: .8rem; border-radius: 1rem; background: #4d8ed8; width: calc(var(--width) * 100%); min-width: 2px; }}
    @media (max-width: 42rem) {{ body {{ padding: 1rem; }} .bar-row {{ grid-template-columns: 1fr 2fr 2rem; font-size: .8rem; }} }}
  </style>
</head>
<body>
<main>
  <h1>Encounter Selection Analysis</h1>
  <div class="callout">
    <p><strong>Research status:</strong> this report records evidence and hypotheses only. It does not change encounter selection in the simulator. {evidence_ceiling}</p>
  </div>
  <div class="cards">
    <div class="card"><strong>{counts["runs"]}</strong>runs</div>
    <div class="card"><strong>{counts["encounters"]}</strong>ordered encounters</div>
    <div class="card"><strong>{counts["ordinary"]}</strong>ordinary selections</div>
    <div class="card"><strong>{counts["manual_adjustments"]}</strong>manual adjustments</div>
  </div>

  <h2>Current findings</h2>
  <p>Adjusted p-values use Holm correction across the predefined primary tests. “Not detected” means this dataset did not distinguish the statistic from its null model; it is not proof of randomness.</p>
  <div class="callout">
    <p><strong>Current interpretation:</strong> {detected_text} The direct model comparison currently favors {model_comparison}. The largest descriptive NPC deviation is <code>{escape(top_npc["npc_id"])}</code>, observed {top_npc["observed"]} times versus {top_npc["expected"]:.2f} expected under uniform eligible-offer selection; the adjusted NPC-level omnibus test does not currently establish that as a replicated weight difference.</p>
  </div>
  <div class="table-wrap"><table aria-label="Current statistical findings">
    <thead><tr><th>Test</th><th>Evidence</th><th>Observed</th><th>Null mean</th><th>Direction</th><th>Adjusted p</th></tr></thead>
    <tbody>{finding_rows}</tbody>
  </table></div>

  <h2>Observed ordinary encounters by NPC</h2>
  <div aria-label="NPC frequency chart">{bars}</div>

  <h2>Largest offer-frequency deviations</h2>
  <p>These rows explain the offer-level discrepancy and are descriptive follow-up hypotheses, not separately tested discoveries.</p>
  <div class="table-wrap"><table aria-label="Largest offer frequency deviations"><thead><tr><th>Offer</th><th>NPC</th><th>Observed</th><th>Expected</th><th>Ratio</th><th>Residual</th></tr></thead><tbody>{offer_residual_rows}</tbody></table></div>

  <h2>Runs</h2>
  <div class="table-wrap"><table aria-label="Run summaries">
    <thead><tr><th>Content-derived ID</th><th>Encounters</th><th>Ordinary</th><th>Adjustments</th><th>Segments</th><th>NPC repeats</th><th>Offer repeats</th></tr></thead>
    <tbody>{run_rows}</tbody>
  </table></div>

  <h2>Most frequent ordinary transitions</h2>
  <div class="table-wrap"><table aria-label="Top NPC transitions"><thead><tr><th>From</th><th>To</th><th>Count</th></tr></thead><tbody>{transition_rows}</tbody></table></div>

  <h2>Eligibility sensitivity</h2>
  <p>The reconstructed-state analysis used {reconstructed["usable"]} ordinary encounters and excluded {reconstructed["incompatible"]} that the current data model considered ineligible. The condition-free sensitivity analysis used {sensitivity["usable"]} and excluded {sensitivity["incompatible"]}.</p>
  <p>A positive NPC-minus-offer log-score difference favors selecting an NPC uniformly before selecting one of its offers. Reconstructed difference: <strong>{_format_number(reconstructed["uniform_npc_minus_offer_bits_per_encounter"])} bits/encounter</strong>; condition-free difference: <strong>{_format_number(sensitivity["uniform_npc_minus_offer_bits_per_encounter"])} bits/encounter</strong>.</p>

  <h2>Data-quality notes</h2>
  <div class="callout warning">
    <p>Offer identity, order, case index, and run boundaries are treated as authoritative. Resources, counters, flags, and eligibility are sensitivity evidence because the game and simulator model may have drifted. Game version and capture context are unknown.</p>
  </div>
  {warning_html}

  <h2>Method</h2>
  <p>Manual adjustments and known cadence, forced, or override encounters are retained in totals but excluded from ordinary-selector tests. Order-only tests shuffle observed NPC/offer pairs within each run segment, preserving marginal counts and preventing transitions across discontinuities. Frequency tests simulate independent choices from each case’s candidate set.</p>
  <p>Primary statistics cover NPC and offer goodness of fit, immediate repetition, longest streak, five-draw diversity, lagged mutual information, within-NPC offer repetition, cadence-slot association, run heterogeneity, and a categorical change-point scan. Recorded analyses use {current["resamples"]:,} deterministic resamples with seed {current["seed"]}. Monte Carlo p-values use <code>(extreme + 1) / (resamples + 1)</code>.</p>
  <p>Research basis: <a href="https://www.itl.nist.gov/div898/handbook/ppc/section2/ppc24.htm">NIST on sparse categorical goodness of fit</a>; <a href="https://gksmyth.github.io/pubs/PermPValuesPreprint.pdf">Phipson and Smyth on valid permutation p-values</a>; <a href="https://doi.org/10.1016/j.physa.2012.12.017">Papapetrou and Kugiumtzis on mutual-information randomization for categorical sequences</a>; and <a href="https://www.itl.nist.gov/div898/handbook/eda/section3/eda35d.htm">NIST on randomness diagnostics</a>.</p>

  <h2>Evidence labels</h2>
  <ul>
    <li><strong>Not detected:</strong> Holm-adjusted p &gt; 0.05.</li>
    <li><strong>Tentative:</strong> adjusted p ≤ 0.05 without at least three independently consistent runs.</li>
    <li><strong>Repeated:</strong> at least three runs, adjusted p ≤ 0.05, and consistent leave-one-run-out direction.</li>
    <li><strong>Model-sensitive:</strong> reconstructed and condition-free eligibility analyses disagree.</li>
  </ul>

  <h2>Snapshot history</h2>
  <div class="table-wrap"><table aria-label="Analysis history"><thead><tr><th>Recorded</th><th>Fingerprint</th><th>Runs</th><th>Ordinary</th><th>Signals</th></tr></thead><tbody>{history_rows}</tbody></table></div>
  <p>Analysis version <code>{escape(current["analysis_version"])}</code>; data SHA-256 <code class="hash">{escape(current["data_hash"])}</code>; snapshot <code class="hash">{escape(current["fingerprint"])}</code>.</p>
</main>
</body>
</html>
"""


def _format_number(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.4f}"
    return escape(str(value))


def _format_p(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return "<0.0001" if value < 0.0001 else f"{value:.4f}"


def write_report(path: Path, history: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(history), encoding="utf-8")
