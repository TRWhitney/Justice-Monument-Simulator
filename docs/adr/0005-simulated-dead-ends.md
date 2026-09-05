# ADR 0005: Resolve arrivals before scoring simulated dead ends

Status: accepted, 2026-09-05.

## Decision

Resolve each future encounter's arrival with that rollout's RNG before selecting
its action. Reuse ADR 0001's reducer preparation with an explicit
`encounter_start` argument so permanent arrival triggers execute exactly once.
The remaining action order, payment gates, penalties, and normalization are shared
with ordinary application. Existing callers keep the default full preparation.

When the realized encounter has no available action, end that simulated path and
apply the existing terminal utility penalty. Never return an unfinished path as
a surviving horizon result. At the root, count random arrivals where the requested
action cannot be applied as failed continuations, rather than dropping their
samples and reporting an expectation conditional on success. This is a conservative
score for that requested action, not a new product rule declaring every failed
payment an actual death. Simulated markers never modify the user's saved state.

## Reconciliation with ADR 0001

An RNG draw is still insufficient proof that an action is impossible or fatal.
Unresolved random arrivals remain eligible before they are realized. Fully
enumerated outcomes can establish certain death, and any surviving branch keeps
a choice eligible against a certainly fatal alternative. This includes Cool
Bird's protected last MH. The UI's conservative action visibility remains intact.

| Alternative | Consequence | Decision |
| --- | --- | --- |
| Stop and score the pre-encounter state | A blocked continuation appears to survive | Reject |
| Declare death from a fixed random preview | Erases viable arrival branches | Reject |
| Resolve arrival once, then choose or terminate | Preserves randomness and accounts for blocked paths | Select |

## Verification

Cover blocked statuses, unavailable payments, surviving random arrivals, root
failure sample counts, and prepared/full reducer equivalence including RNG draws.
Keep the existing custom-data affordability and constraint fallback coverage.
