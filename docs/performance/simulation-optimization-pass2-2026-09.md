# Simulation optimization, second pass

## Scope and method

This pass implements individual health-probe reuse (ADR 0010), static encounter
indexes and shared condition setup (ADR 0011), and local action-result reuse
(ADR 0012). The default horizon stays at 20. Root rollout counts, adaptive
sampling, risk weights, and the bounded future-choice policy are unchanged.

Compare against archived commit `9e7254b`, which already includes the first
optimization pass. These are additional gains over that implementation.
Measurements use Python 3.12.3, builtin data and suggested rules, and the
Scripticus: Kitchen Loan recommendation. Each timing measures `recommend` only,
excluding loading, planner construction, worker startup, and UI rendering.
Benchmarks ran serially and separately from test suites on the same machine.

The full default-size recommendation fell from 102.300 to 77.422 seconds, a
24.3% reduction. Both runs used 200 samples per action with adaptive sampling
enabled; neither needed a top-up. Their complete score/sample SHA-256 matches:

`70fbf18ec7ef7d4db56e8bc64c466f4b92c49b254b6ba09901f10fdc8558799f`

## Scenario matrix

- `baseline`: case 11, 50 coins, 20 popularity, 8 health, 2 dismissals, no contracts.
- `low-health`: the baseline with 1 health; retains enough resources to exercise
  future decisions instead of dying at the immediately following Harbinger.
- `loan`: the baseline after approving Kitchen Loan, including its actual saved
  repayment trigger and changed resources/case.
- `due-event`: the baseline with a case-16 bill deducting 2 health and 15 coins.
- `override`: the baseline with a three-use chest-magnetizer encounter override.

Short probes use five root samples per eligible action with adaptive sampling
disabled. They measure runtime and deterministic equivalence, not recommendation
quality. All 16 comparisons below have identical complete recommendation hashes,
including every utility sample. Timings are individual observations, not latency
guarantees; repeat them on the intended hardware when choosing budgets.

| Scenario | Seed | Horizon | Samples/action | Before (s) | After (s) | Time reduction |
| --- | --- | --- | --- | --- | --- | --- |
| baseline | 42 | 20 | 5 | 2.772 | 2.104 | 24.1% |
| baseline | 42 | 20 | 200 | 102.300 | 77.422 | 24.3% |
| baseline | 42 | 40 | 5 | 10.917 | 8.061 | 26.2% |
| due-event | 42 | 20 | 5 | 3.328 | 2.512 | 24.5% |
| due-event | 42 | 40 | 5 | 10.122 | 7.184 | 29.0% |
| loan | 42 | 20 | 5 | 3.767 | 2.857 | 24.1% |
| loan | 42 | 40 | 5 | 13.936 | 10.200 | 26.8% |
| low-health | 42 | 20 | 5 | 1.824 | 1.217 | 33.3% |
| low-health | 42 | 40 | 5 | 4.229 | 2.868 | 32.2% |
| override | 42 | 20 | 5 | 2.294 | 1.656 | 27.8% |
| override | 42 | 40 | 5 | 10.176 | 7.461 | 26.7% |
| baseline | 77 | 20 | 5 | 2.137 | 1.512 | 29.3% |
| due-event | 77 | 20 | 5 | 2.579 | 1.704 | 33.9% |
| loan | 77 | 20 | 5 | 2.608 | 1.962 | 24.8% |
| low-health | 77 | 20 | 5 | 2.347 | 1.523 | 35.1% |
| override | 77 | 20 | 5 | 1.553 | 1.245 | 19.8% |

## Reproduce

```bash
uv run python scripts/benchmark_planner.py --horizons 20 40 \
  --rollouts 5 --no-adaptive \
  --scenarios baseline low-health loan due-event override \
  --output /tmp/justice-scenario-matrix.json

uv run python scripts/benchmark_planner.py --horizons 20 \
  --rollouts 5 --no-adaptive --seed 77 \
  --scenarios baseline low-health loan due-event override \
  --output /tmp/justice-second-seed.json

uv run python scripts/benchmark_planner.py --horizons 20 \
  --output /tmp/justice-default-size.json
```

For reference comparisons, export `9e7254b` into an isolated directory and run
this version of the benchmark script with `PYTHONPATH` pointing at that export's
`src`. Use the same Python environment and compare state, configuration, seed,
and score hash. The script never reads a personal run and writes JSON only when
an explicit output path is supplied.

## Verification boundaries

`./scripts/validate_repo.sh` passed formatting, lint, both schemas, 358 marked
unit tests, 69 GUI tests, and the smoke launch. A separate directly affected test
run passed 200 unit tests. No retries were needed and tracked review artifacts
were unchanged.

New unit tests compare health-cache results with full reductions over builtin
outcomes, active agreements, payment/health boundaries, fractional resources,
floors, action blocks, required actions, due events, and custom dependencies.
They also verify cache bounds, replaced definitions, and pickle round trips used
by spawned planner workers. Encounter tests preserve probability order and row
multiplicity while checking live model weights and custom override targets.
Action tests check shared immediate evaluations and sole-action choices; existing
random-transition tests retain real RNG draws even for single-branch randomness.

The broader immutable state-key refactor and separate policy-comparison depth
remain deferred. Complex health dependencies keep the existing reducer path;
static indexes assume definitions remain immutable within a dataset lifetime.
