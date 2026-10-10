# CPU efficiency

## Destination
[Specification](spec.md), [ticket](tickets/01-encounter-reuse.md),
[proof](../../docs/adr/0023-reuse-exact-predicate-inputs.md) and
[measurements](../../docs/headless/latency.md).

## Current state
Delivered. Validation and independent intent/engineering reviews passed with no
findings. Lower CPU work takes priority over parallel throughput; the default
remains one process.

## Progress
Bounded exact eligibility and uniform proposals, typed numeric probabilities,
ordered risk sums, health-only reducer probes and constructor-based state copies.
Focused red-green checks covered reuse and bookkeeping, followed by input/error,
RNG and complete-result equivalence checks. Initial test-fixture mistakes were
corrected before implementation evidence was accepted.

## Accepted sources
Latest user intent and original headless preservation requirements; specification
and ADRs linked above. Broader continuation and transition memoization were
rejected after low reuse; conclusions remain in the canonical measurements.

## Verification
`./scripts/validate_repo.sh` passed formatting, lint, both schemas, 489 unit tests,
69 GUI tests and smoke. Direct affected checks passed 142 tests across encounter
indexes, effects, health/risk, state copies, planner/headless and workers.
Three alternating full-budget runs against 52c6010 matched complete seeded
recommendations and reduced median single-process CPU time by 15.7%. Five further
seed-77 scenarios matched complete samples. Installed-wheel tests passed in the
gate. HTML comparison inspected at 728px light and 360px dark; measurement, worker,
batch and export interactions passed in the collaborative browser.

## Out of scope
Extra concurrency, reduced accuracy/budgets, native build dependencies and thermal
controls. Temperature and power were not measured.

## Continuation
Branch main, reference 52c6010. No accepted work remains. Resume with
`python3 /home/whitney-white/.codex/skills/work-system/scripts/navigate.py resume novel-work delivery`.
Owned paths: this effort record, focused engine/model/util changes, benchmark,
affected unit tests, and the linked headless/ADR documentation. Disposable outputs have been discarded.


## History
- c6b5033 `[Optimization] Reuse encounter eligibility`
- 4108926 `[Optimization] Cache resource probabilities`
- 1e7bacf `[Optimization] Skip health probe bookkeeping`
- bb256d1 `[Optimization] Reuse ordered risk sums`
- 8474c3f `[Optimization] Copy states positionally`
- fdb0524 `[Tweak] Report planner CPU seconds`

The final documentation commit records this proof and completion index. No history
was rewritten; no intentionally uncommitted work remains.
