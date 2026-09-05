# State comparison and immutable contract verification

## Scope

This implements item 4 of the optimization audit:

- Named state and contract keys replace positional tuple slicing and temporary
  states used only for non-resource comparisons (ADR 0013).
- Owned immutable nested payloads make cached effect and contract keys safe to
  reuse. Expression readers, JSON exports, and worker pickling retain their
  behavior (ADR 0014).
- Case advancement keeps unchanged collections and copies them only when timers
  change or events fire (ADR 0015).

The horizon remains 20. Sampling budgets, risk weights, and future-policy depth
are unchanged. Item 5 and a wholesale game-state redesign remain deferred.

## Compatibility and safety

StateKey retains the previous full tuple's fields, order, equality, and hash.
Contracts retain labels, payloads, conditions, and event/trigger order. Resource
changes share canonical contract keys; changed contracts create new ones.
Constructors detach nested dictionaries/lists from their mutable inputs, and
programmatic nested effect records normalize to the same raw payload structure.
Full state keys are not memoized: current counters, floors, and status mappings
continue to contribute their current values.

JSON run versions and field shapes are unchanged. Recursive export produces
independent ordinary containers, including nested effects, probabilities, and
status data. Pickle round trips reconstruct immutable backing maps and retain
valid populated keys. GUI checks cover numeric effect display, unresolved
formula text, search-card reuse, Mid worker completion, and manual transitions.

## Verification

Each implementation outcome passed `./scripts/validate_repo.sh` before commit.
The final gate passed formatting, lint, both schemas, 377 unit tests, 69 GUI
tests, and smoke launch. Direct checks passed 30 tests for named keys, 134 for
immutable-payload integration followed by 8 focused tests after adding nested
record compatibility, and 129 for case advancement and affected engine/planner
paths. A separate affected GUI run passed 16 tests. No failing run was retried.

Explicit GUI artifact workflows produced four inspected images in
`/tmp/justice-state-review`: Grumblo cards at two scales, a completed cached Mid
recommendation, and the state awaiting the next manual offer. No tracked review
artifacts changed. This native Qt project has no Playwright suite.

## Benchmark method

Compare against archived commit `89a2049`, which includes the previous two
optimization passes. Use Python 3.12.3, builtin data and suggested rules, and
Scripticus: Kitchen Loan. Timings measure recommendation computation only;
loading, planner construction, worker startup, and GUI rendering are excluded.
Benchmarks run serially and separately from verification suites.

Short probes use five samples per eligible action without adaptive sampling.
Baseline state is case 11 with 50 coins, 20 popularity, 8 health, 2 dismissals,
and no commitments. The loan scenario starts after actual Kitchen Loan approval;
the due-event scenario schedules a case-16 health/coin bill. These small probes
measure equivalence and runtime, not recommendation quality.

All ten comparisons preserve every recommendation field and utility sample
exactly. The full-size run used 200 samples per action with adaptive sampling
enabled; neither implementation needed a top-up. Runtime changed from 77.541
to 77.065 seconds (about 0.6%). Treat that as essentially flat performance,
not an established speedup. Individual short probes also show only small
changes, including slight regressions in some rows; differences this small can
reflect run-to-run timing variation.

This pass improves ownership, cache safety, and comparison structure. It is not
a basis for raising the default horizon or promising substantially lower Mid
recommendation latency. Eliminating repeated key construction is partly offset
by immutable-container reads and construction.

| Scenario | Seed | Horizon | Samples/action | Before (s) | After (s) |
| --- | --- | --- | --- | --- | --- |
| baseline | 42 | 20 | 5 | 2.115 | 2.110 |
| baseline | 42 | 20 | 200 | 77.541 | 77.065 |
| baseline | 42 | 40 | 5 | 8.127 | 8.134 |
| due-event | 42 | 20 | 5 | 2.527 | 2.493 |
| due-event | 42 | 40 | 5 | 7.251 | 7.221 |
| loan | 42 | 20 | 5 | 2.883 | 2.844 |
| loan | 42 | 40 | 5 | 10.291 | 10.193 |
| baseline | 77 | 20 | 5 | 1.476 | 1.473 |
| due-event | 77 | 20 | 5 | 1.694 | 1.694 |
| loan | 77 | 20 | 5 | 1.940 | 1.947 |

The full-size recommendation hash remains:

`70fbf18ec7ef7d4db56e8bc64c466f4b92c49b254b6ba09901f10fdc8558799f`


## Reproduce

```bash
uv run python scripts/benchmark_planner.py --horizons 20 40 \
  --rollouts 5 --no-adaptive --scenarios baseline loan due-event \
  --output /tmp/justice-state-matrix.json

uv run python scripts/benchmark_planner.py --horizons 20 --seed 77 \
  --rollouts 5 --no-adaptive --scenarios baseline loan due-event \
  --output /tmp/justice-state-second-seed.json

uv run python scripts/benchmark_planner.py --horizons 20 \
  --output /tmp/justice-state-default.json
```

For the reference, run the archived benchmark script with `PYTHONPATH` pointing
to the archive's `src`, using the same Python environment. Compare seed, state,
configuration, and SHA-256 of every recommendation field and utility sample.
Artifacts are synthetic and generated only at explicitly supplied output paths.
