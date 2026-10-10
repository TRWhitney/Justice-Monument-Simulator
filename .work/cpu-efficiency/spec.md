# Reduce CPU work per recommendation

## Problem statement
Whitney prioritizes efficiency and reduced CPU demand because long calculations
make the CPU hot. Parallel throughput is useful but does not meet this priority.

## Solution
Optimize demonstrated shared-core repeated work, measure CPU and elapsed seconds
with one worker, and preserve complete seeded results. First reuse encounter
eligibility and immutable uniform proposal weights through exact predicate
dependencies. Keep mutable model weights and ordered replacements live. Extend
existing reducer health-only probes to deterministic resource outcomes when no
chain, later trigger or due event can affect health. Reuse resource-only numeric
probabilities through exact typed inputs and the existing safe evaluator; scaling
and contract-dependent formulas keep their full contexts. Reuse an ordered risk
sum only for the identical immutable pool safety and live replacement probability.
Copy ordinary states through positional constructor arguments only when their
field order matches; retain constructor validation and general fallback.

## User stories
1. As an overlay consumer, I want each recommendation to require less CPU work
   while retaining configured horizon, sampling and simulation accuracy.

## Implementation decisions
Preserve GUI/CLI behavior, worker defaults, risk settings, rules, prepared-root
handling, adaptive budgets, sample sequences, cancellation and public extension
seams. Cache only fully determined values with bounded retention. Resource and
counter comparisons may share their exact truth values; arithmetic or dynamic
expressions retain complete referenced inputs. Flags, statuses and pending labels
remain live. Reuse the existing selector and expression evaluator on misses.
Consult ADRs 0006, 0010, 0016, 0018, 0021 and 0022. No extra workers, throttling,
shortened horizons, dropped branches or reduced sampling as a substitute for
less work. Measure CPU demand rather than claiming a measured temperature change.

## Testing decisions
Observe focused red-green tests at public encounter/planner seams. Compare ordered
probabilities, selected encounters and RNG draws against uncached evaluation with
custom conditions, histories, active contracts and mutable model weights. Verify
bounded retention and independent returned collections. Run affected unit tests
and the full gate. Compare complete recommendations and CPU/wall timings against
52c6010, with one worker and the unchanged 32-per-action, 20-case workload.

## Out of scope
Thermal control, host-game integration, policy approximation, changed defaults,
automatic worker selection and native build dependencies.
