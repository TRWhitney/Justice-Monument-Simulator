from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from justice_sim.analysis.encounter_selection import (
    HISTORY_VERSION,
    Observation,
    ParsedRun,
    RunParseError,
    analyze_runs,
    deduplicate_runs,
    evidence_label,
    holm_adjust,
    parse_run,
    record_snapshot,
    render_report,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "encounter_runs"


def _observation(
    case_index: int,
    offer_id: str,
    npc_id: str,
    *,
    run_id: str = "run-a",
    segment: int = 1,
    reconstructed: tuple[str, ...] = ("offer1", "offer2"),
    all_offers: tuple[str, ...] = ("offer1", "offer2"),
) -> Observation:
    return Observation(
        run_id=run_id,
        segment=segment,
        case_index=case_index,
        offer_id=offer_id,
        npc_id=npc_id,
        action="approve",
        pre_state={"case_index": case_index},
        exclusion_reason=None,
        eligible_reconstructed=reconstructed,
        eligible_all_offers=all_offers,
    )


def _run(
    run_id: str,
    source_hash: str,
    observations: list[Observation],
) -> ParsedRun:
    return ParsedRun(
        run_id=run_id,
        source_hash=source_hash,
        log_entries=len(observations),
        manual_adjustments=0,
        observations=tuple(
            replace(observation, run_id=run_id) for observation in observations
        ),
        segment_count=max(observation.segment for observation in observations),
    )


@pytest.mark.unit
def test_parse_run_preserves_order_and_marks_nonordinary_records(data_factory):
    parsed = parse_run(FIXTURES / "synthetic_run.json", data_factory())

    assert [item.case_index for item in parsed.observations] == [1, 2, 3, 4, 5, 7]
    assert parsed.manual_adjustments == 1
    assert parsed.segment_count == 2
    assert [item.case_index for item in parsed.ordinary] == [1, 2, 3, 4, 7]
    assert parsed.observations[4].exclusion_reason == "cadence"
    assert "sequence discontinuity" in parsed.warnings[0]


@pytest.mark.unit
def test_parse_run_rejects_malformed_json(data_factory):
    with pytest.raises(RunParseError, match="invalid JSON"):
        parse_run(FIXTURES / "malformed.txt", data_factory())


@pytest.mark.unit
def test_duplicate_run_content_is_not_counted_twice(data_factory):
    parsed = parse_run(FIXTURES / "synthetic_run.json", data_factory())

    runs, duplicates = deduplicate_runs([parsed, parsed])

    assert runs == [parsed]
    assert duplicates == [parsed.run_id]


@pytest.mark.unit
def test_analysis_is_deterministic_and_does_not_cross_run_boundaries(data_factory):
    observations = [
        _observation(1, "offer1", "npc1"),
        _observation(2, "offer2", "npc2"),
    ]
    first = _run("run-a", "a" * 64, observations)
    second = _run("run-b", "b" * 64, observations)

    result = analyze_runs(
        [first, second], data_factory(), data_hash="c" * 64, resamples=29, seed=7
    )
    repeated = analyze_runs(
        [first, second], data_factory(), data_hash="c" * 64, resamples=29, seed=7
    )

    assert result == repeated
    assert result["order"]["observed"]["npc_repeats"] == 0
    assert all(test["p_value"] > 0 for test in result["order"]["tests"])


@pytest.mark.unit
def test_clustered_and_cooldown_sequences_have_opposite_repeat_directions(
    data_factory,
):
    clustered = _run(
        "run-clustered",
        "d" * 64,
        [
            _observation(index, offer_id, npc_id)
            for index, (offer_id, npc_id) in enumerate(
                [("offer1", "npc1")] * 4 + [("offer2", "npc2")] * 4,
                start=1,
            )
        ],
    )
    cooldown = _run(
        "run-cooldown",
        "e" * 64,
        [
            _observation(index, offer_id, npc_id)
            for index, (offer_id, npc_id) in enumerate(
                [("offer1", "npc1"), ("offer2", "npc2")] * 4,
                start=1,
            )
        ],
    )

    clustered_result = analyze_runs(
        [clustered], data_factory(), data_hash="f" * 64, resamples=49, seed=3
    )
    cooldown_result = analyze_runs(
        [cooldown], data_factory(), data_hash="f" * 64, resamples=49, seed=3
    )
    clustered_repeat = clustered_result["conclusions"][2]
    cooldown_repeat = cooldown_result["conclusions"][2]

    assert clustered_repeat["direction"] == "higher"
    assert cooldown_repeat["direction"] == "lower"


@pytest.mark.unit
def test_model_drift_is_reported_as_reconstructed_incompatibility(data_factory):
    observation = _observation(
        1,
        "offer1",
        "npc1",
        reconstructed=("offer2",),
        all_offers=("offer1", "offer2"),
    )
    run = _run("run-drift", "1" * 64, [observation])

    result = analyze_runs(
        [run], data_factory(), data_hash="2" * 64, resamples=9, seed=1
    )

    assert result["frequency"]["reconstructed"]["usable"] == 0
    assert result["frequency"]["reconstructed"]["incompatible"] == 1
    assert result["frequency"]["all_offers_sensitivity"]["usable"] == 1


@pytest.mark.unit
def test_holm_adjustment_and_evidence_classification():
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert evidence_label(0.2, 10) == "not detected"
    assert evidence_label(0.01, 2) == "tentative"
    assert evidence_label(0.01, 3, leave_one_run_out_consistent=True) == "repeated"
    assert evidence_label(0.2, 3, model_sensitive=True) == "model-sensitive"


@pytest.mark.unit
def test_snapshot_history_deduplicates_and_report_escapes_content(data_factory):
    run = _run(
        "run-a",
        "3" * 64,
        [_observation(1, "offer1", "npc1")],
    )
    snapshot = analyze_runs(
        [run], data_factory(), data_hash="4" * 64, resamples=9, seed=1
    )
    snapshot["warnings"] = ["<script>alert('unsafe')</script>"]
    history = record_snapshot({"version": HISTORY_VERSION, "snapshots": []}, snapshot)
    duplicate = record_snapshot(history, snapshot)

    assert len(duplicate["snapshots"]) == 1
    next_snapshot = dict(snapshot)
    next_snapshot["fingerprint"] = "new-input-fingerprint"
    extended = record_snapshot(duplicate, next_snapshot)
    assert len(extended["snapshots"]) == 2
    report = render_report(duplicate)
    assert "&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;" in report
    assert "<script>alert('unsafe')</script>" not in report
    assert "Current statistical findings" in report


@pytest.mark.unit
def test_fixture_is_valid_json_for_clear_failure_diagnostics():
    payload = json.loads((FIXTURES / "synthetic_run.json").read_text(encoding="utf-8"))
    assert payload["version"] == "run_state_v1"
