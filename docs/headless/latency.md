# Headless planner latency

Measured on Python 3.12.3, Kitchen Loan root offer, seed 42, state
`GameState(11, 50, 20, 8, 2, 0)`, builtin suggested rules, 32 samples for each
of approve/reject/dismiss, and a 20-case horizon. Adaptive sampling is disabled
for this fixed-budget workload only. Production defaults are unchanged.
Timers cover recommendation work, excluding imports and data loading.

## Profile

The initial detached reproduction took 13.268 seconds on this machine. The
reported 11.186-second run was on a different run/environment and is not used
as the local before/after baseline.

A cProfile run measured 32.959 seconds inside recommendation, including profiler
overhead. Projected client risk accounted for 18.399 seconds of cumulative time,
including 15.893 seconds in the risk loop. Health probes accounted for 10.499
seconds and client encounter distributions for 8.661 seconds. These times overlap
and must not be added together.

After the restricted health-cache/payment-region optimization and dismissal-first
risk checks, the corresponding profile measured 30.546 seconds inside
recommendation. Health-probe cumulative time fell to 8.221 seconds. Reducer health
probe calls fell from 243,688 to 139,266. The complete recommendation hash matched.

The optimization preserves reducer rules, full-depth policy continuations,
probability integration, RNG streams, scoring weights and sample budgets.
Broader continuation memoization was explored but had too little benefit to
retain. No policy or horizon approximation was added.

## Repeated timings

Three alternating before/after runs compare the original health cache and risk
probe order from commit `adfec5317f25b6cafeaaf9c32ec4c224549e58fa` with the changed
versions. Each run constructs a fresh planner. The current synchronous sample
collection code is common to both sides; the initial unchanged-checkout run
provides an additional baseline. Benchmark runs are kept separate from the
repository gate and other sustained workloads.

| Run | Original cache/order | Changed cache/order |
| --- | ---: | ---: |
| 1 | 13.208 s | 12.201 s |
| 2 | 12.545 s | 12.333 s |
| 3 | 13.017 s | 12.532 s |
| Median | 13.017 s | 12.333 s |

The median reduction is 0.684 seconds, about 5.3%. This is a modest local gain;
full-depth future-policy evaluation remains expensive. It does not establish a
universal latency bound or improved recommendation accuracy.

All six runs used 32 observations per action and produced the same SHA-256 over
the complete recommendation, including every utility sample:

```text
b3ae0eb38bab53acbdac0eb8657f8bf542b7835adb78561f3b035fe1e327ade6
```

Run the current workload with:

```sh
uv run python scripts/benchmark_planner.py --horizons 20 --rollouts 32 --no-adaptive
uv run python -m cProfile -o /tmp/headless.prof scripts/benchmark_planner.py --horizons 20 --rollouts 32 --no-adaptive
uv run python -c 'import pstats; pstats.Stats("/tmp/headless.prof").strip_dirs().sort_stats("cumtime").print_stats(35)'
```

[Machine-readable timing evidence](benchmark.json) records individual runs,
configuration, sample counts, hashes and incremental timing.

## Incremental response

The same workload with `batch_size=1` emitted its first estimate in 0.387 seconds,
with one observation per action. It completed in 12.630 seconds with all 32
observations per action and the same complete recommendation hash. Intermediate
reporting improves time to first evidence without reducing the final work.
Cancellation remains cooperative between batches, not a wall-clock guarantee.
