# Exact risk pool speed

## Destination
[Specification](spec.md), [core ticket](tickets/01-risk-pool.md) and
[worker ticket](tickets/02-workers.md).

## Current state
Delivered. Exact shared-core reuse and optional CPU workers are validated and independently reviewed.

## Progress
Exact region proof, live ordered probability arithmetic, inactive case-only
trigger guards and full evaluator fallback. Worker count defaults to one. Spawned
sampling preserves absolute indices, adaptive boundaries and ordered aggregation.
Cancellation, close and exceptions release workers. Installed-wheel sampling blocks
Qt in the parent and children. Focused red-green coverage is passing.

## Accepted sources
User request and prior headless requirements; explicit acceptance of optional CPU
workers; ADRs 0006, 0010, 0011, 0016, 0019, 0020, [0021](../../docs/adr/0021-reuse-exact-harbinger-pool-safety.md)
and [0022](../../docs/adr/0022-opt-in-rollout-cpu-workers.md).

## Verification
Focused affected tests pass. Comparison and profile conclusions are retained in
[latency](../../docs/headless/latency.md); raw outputs are disposable.
The first full gate found an obsolete serialization-count expectation for plain
states. Its coverage now targets the complex fallback; the fast path independently
proves zero serialization. The final gate passed 471 unit and 69 GUI tests, formatting, lint, schemas and smoke.
Direct affected checks passed 96 tests. Independent intent and engineering reviews passed with no findings.

## Out of scope
Reduced horizon, samples or policy accuracy, GUI changes and native build dependencies.

## Continuation
Branch `main`, reference `4054637`. Resume with
`python3 /home/whitney-white/.codex/skills/work-system/scripts/navigate.py resume novel-work delivery`.
No accepted work remains. Temporary study outputs have been discarded; retain the
linked conclusions and reusable source/tests.
Owned paths: `.work/risk-pool-speed/`, risk pool/scoring, planner workers/rollout,
benchmark script, affected unit tests and docs under headless/ADR folders.
