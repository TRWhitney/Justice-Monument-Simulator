# 01 Reduce repeated encounter eligibility work

**What to build:** Lower CPU cost per unchanged recommendation through exact
encounter eligibility and static proposal reuse.

**Blocked by:** none

**Status:** delivered

- [x] Reuse equivalent eligibility without freezing live predicate inputs or model configuration.
- [x] Preserve encounter ordering, full probabilities, RNG streams and complete seeded recommendations.
- [x] Bound caches, preserve extension dispatch and return independent collections.
- [x] Measure one-worker CPU and elapsed seconds; pass affected tests and the gate.

## Accepted sources
[Specification](../spec.md), Whitney's efficiency priority and existing policy ADRs.

## Completion evidence
See [status](../status.md) for the gate and direct checks, and
[measurements](../../../docs/headless/latency.md) for CPU/time and full-result
comparisons. Shared-core risk, numeric, health and copy improvements follow the
same preservation boundary.
