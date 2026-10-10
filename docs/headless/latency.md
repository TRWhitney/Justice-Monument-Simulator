# Headless planner latency

Measured on Python 3.12.3 with Kitchen Loan, seed 42, builtin suggested rules,
`GameState(11, 50, 20, 8, 2, 0)`, 32 samples per action and a 20-case horizon.
Adaptive sampling is disabled for this fixed-budget study. Production defaults,
risk settings, simulation rules and full-depth policy evaluation remain unchanged.

## Comparison

Three alternating runs compare unchanged reference commit `4054637`, loaded from
a temporary source archive, with the optimized core and optional CPU workers.
Each constructs a fresh planner. Timers include worker startup and shutdown,
and exclude parent imports and data loading. No other sustained workloads ran
alongside the measurements.

| Run | Reference | Core, one worker | Four workers | Eight workers |
| --- | ---: | ---: | ---: | ---: |
| 1 | 11.863 s | 8.538 s | 3.224 s | 2.306 s |
| 2 | 12.053 s | 8.888 s | 3.265 s | 2.181 s |
| 3 | 11.751 s | 8.622 s | 3.204 s | 2.294 s |
| Median | 11.863 s | 8.622 s | 3.224 s | 2.294 s |

Core reuse reduces median time by 27.3%. Four workers give a 3.68-fold speedup;
eight give 5.17-fold. All twelve complete recommendations, including every
sampled utility, match. The earlier payment-probe optimization alone achieved
about 5.3%; the reported 11.186-second detached run came from another environment.
These local results are not a universal latency bound. Workers compete for CPU
with the host game and overlay; startup can outweigh gains for small decisions.

## Profile and behavior

Profiling the reference took 31.186 recommendation seconds and identified
repeated projected Harbinger risk as the main cost. The final core profile took
20.827 seconds. Projected risk fell from 17.628 to 8.582 cumulative seconds;
health-cache checks from 883,921 to 91,967; reducer health probes from 139,266 to
76,394; encounter distribution scans from 132,080 to 49,186. Future-action choice
still ran 40,142 times. Profiler overhead is excluded from the throughput table.

The cache reuses exact payment and eligibility regions, keeps replacement
probabilities live and preserves ordered arithmetic. False case-only trigger
guards permit reuse for inactive arrivals. Complex definitions and states fall
back to the full evaluator. Workers preserve absolute sample indices, adaptive
boundaries and aggregation order. See [core proof](../adr/0021-reuse-exact-harbinger-pool-safety.md)
and [worker ownership](../adr/0022-opt-in-rollout-cpu-workers.md).

Additional incremental runs matched the same complete samples:

| Workers | Batch per action | First estimate | Complete |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 0.299 s | 8.338 s |
| 4 | 1 | 0.314 s | 3.559 s |
| 8 | 4 | 0.787 s | 2.440 s |

These are individual latency examples. The larger batch initially reports four
observations per action, the others one. Cancellation remains between batches.

Use the [configurable execution comparison](../adr/planner-execution-options.html)
and [public API](api.md). Rerun the reusable workload with:

```sh
uv run python scripts/benchmark_planner.py --horizons 20 --rollouts 32 --no-adaptive --workers 4
```

Raw run output, temporary reference snapshots and profiles are disposable.
