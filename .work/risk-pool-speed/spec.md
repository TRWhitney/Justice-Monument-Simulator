# Faster exact projected risk

## Problem statement
The headless 32-sample, three-action, 20-case workload remains about twelve seconds. Projected client Harbinger risk dominates repeated inner policy scoring.

## Solution
Reuse proved equivalent pool safety decisions across exact resource payment regions. Keep the existing reducer as the miss evaluator and the full risk evaluator as fallback. Preserve ordered probability arithmetic and complete seeded recommendations.

## User stories
1. As an overlay developer, I want substantially lower recommendation latency while keeping the configured accuracy, horizon and sampling behavior.

## Implementation decisions
Retain synchronous and incremental interfaces, default configuration, policy branch integration and RNG streams. A narrow deterministic pool cache may classify resources by exact affordability and eligibility boundaries. Keep continuous replacement probabilities live. Unknown expressions, resource-changing arrivals and active contracts that can affect these probes must fall back. Cache ownership, bounded retention, reset and worker serialization follow existing planner caches. No approximate state merging. Whitney explicitly accepted optional CPU workers alongside core optimizations. Add a `workers` keyword defaulting to one to the existing recommendation APIs. Spawn worker processes only for sampled work, pair absolute sample indices across actions, and aggregate in original order. Keep adaptive decisions and cancellation at batch boundaries. Builtin stable encounter models are supported; custom models retain single-process dispatch. Require the standard main guard for process spawning. Worker exceptions must propagate and workers must shut down when iteration completes, closes, cancels or fails.

## Testing decisions
Compare against the uncached risk evaluator and complete full-reducer probes at boundaries, fractional balances, floors, blocks, histories and active contracts. Test unsupported data/state fallback, reset, serialization and bounded retention. Compare complete recommendation hashes across scenarios, seeds and incremental batches. Run the required repository gate and affected tests. Record repeated alternating before/after timings outside the gate. Aim for at least a twofold local speedup; report actual results and limits rather than treating that aim as a universal promise.

## Out of scope
Changing defaults, reducing work budgets, horizon or policy accuracy, changing GUI behavior, native build dependencies and overlay integration.
