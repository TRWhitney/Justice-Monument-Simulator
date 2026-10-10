# Headless planner latency and CPU cost

Python 3.12.3, Kitchen Loan, seed 42, builtin suggested rules and
`GameState(11, 50, 20, 8, 2, 0)`. The fixed workload uses one process, three
actions, 32 samples per action and a 20-case horizon. Adaptive sampling is disabled
only for this study. Production defaults, risk, rules and policy depth are unchanged.

## CPU efficiency

Three alternating runs compare `52c6010` with ADR 0023's shared-core optimizations.
Each run constructs a fresh planner. Imports and data loading precede the timers;
recommendation work is included. The previous source is loaded from a disposable
archive outside the checkout. No sustained workload runs alongside measurements.

| Run | Previous elapsed | Optimized elapsed | Previous CPU | Optimized CPU |
| --- | ---: | ---: | ---: | ---: |
| 1 | 8.357 s | 7.019 s | 8.354 s | 7.017 s |
| 2 | 8.263 s | 7.044 s | 8.261 s | 7.043 s |
| 3 | 8.395 s | 7.199 s | 8.391 s | 7.193 s |
| Median | 8.357 s | 7.044 s | 8.354 s | 7.043 s |

Median CPU work falls 15.7%; elapsed time falls 15.7%. This is a further efficiency
gain, not a dramatic acceleration. Every complete recommendation, including each
sampled utility, matches. Five further eight-sample, horizon-20 scenarios at seed
77 also match: baseline, low health, loan, due event and override. Temperature,
power and host-game contention were not
measured; lower CPU seconds do not prove a lower peak temperature.

The fresh initial profile identifies repeated encounter eligibility, numeric
probability contexts, state copies and health-risk reduction. Exact predicate
inputs and immutable uniform proposals avoid repeated scans. Resource-only
probabilities retain typed inputs and zero signs. Health-only probes skip next-state
bookkeeping when it cannot affect health. Identical pool safety/probability pairs
reuse their ordered risk sum. Positional state copies still run the constructor.
Complex cases keep the full evaluators. See [proof and limits](../adr/0023-reuse-exact-predicate-inputs.md).

Continuation memoization hit 28 of 1002 probes; action-transition memoization hit
1047 of 34263 full keys, or 1194 with unreferenced counters removed. Both were
rejected because their low reuse did not justify serialization and correctness cost.

## Earlier throughput measurements

These median elapsed times belong to the earlier `4054637` to `52c6010` study;
worker CPU totals were not measured. They do not establish efficiency gains from
parallelism or predict worker timings for the latest core.

| Reference | Earlier core, one process | Four workers | Eight workers |
| ---: | ---: | ---: | ---: |
| 11.863 s | 8.622 s | 3.224 s | 2.294 s |

All twelve complete recommendations matched. The earlier core reduced elapsed
time 27.3%. Workers shorten wall time by using more CPU concurrently and separate
caches. One process remains the default. The reported detached 11.186-second run
came from another environment; these local timings are not universal bounds.

Use the [configurable comparison](../adr/planner-execution-options.html) and
[public API](api.md). Rerun the fixed workload with:

```sh
uv run python scripts/benchmark_planner.py --horizons 20 --rollouts 32 --no-adaptive --workers 1
```

The script reports parent CPU and, where available, completed-child CPU separately.
Multi-worker total CPU is unavailable on platforms without child accounting;
parent CPU alone is never reported as the worker total. Raw output, archives and
profiles are disposable.

## CPU pacing

The bounded pacing experiment used the same fixed workload with fresh
subprocesses, three rotated passes per setting and two-second gaps. A temporary
action-selection hook checked thread CPU time, including continuation decisions.
Imports and setup preceded the recommendation timers. All twelve complete
recommendations and utility samples matched.

| Pacing after about 50 ms CPU | Median elapsed | Median CPU | Median core busy | Median run-average package temperature |
| --- | ---: | ---: | ---: | ---: |
| None | 7.055 s | 7.053 s | 99.9% | 67.4°C |
| Timer only | 7.039 s | 7.035 s | 99.9% | 67.5°C |
| 2 ms | 7.505 s | 7.205 s | 96.0% | 66.2°C |
| 5 ms | 7.999 s | 7.261 s | 90.8% | 62.2°C |

CPU duty is CPU seconds divided by elapsed seconds, relative to one core.
The 5 ms pauses added 0.944 s, or 13.4%, without reducing measured CPU work.
Actual sleeps averaged 5.08 ms. The timer-only control stayed within timing
variation. Whitney selected 5 ms as the configurable default duration when pacing
is enabled. Existing calls remain unpaced.

Package temperature was sampled every 200 ms across each subprocess lifetime,
including startup. Unpaced peaks ranged from 74–79°C; 5 ms peaks ranged from
73–75°C. Short runs, incomplete order balancing, thermal carryover, migration and
host activity limit attribution. Lower observed averages do not prove cooling
during sustained Idleon play. The [Linux sensor documentation](https://docs.kernel.org/hwmon/coretemp.html)
describes the package readings.

This experiment does not predict multi-worker temperature or power.
