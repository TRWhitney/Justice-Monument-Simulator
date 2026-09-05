# ADR 0006: Bound extra lookahead for choices with future effects

Status: accepted, 2026-09-05.

## Decision

Keep the configured horizon, root rollout counts, adaptive sampling, and risk
weights unchanged. At a future choice, reuse exact immediate outcomes for
eligibility and scoring. Ordinary resource choices keep immediate expected-value
selection. If eligible outcomes differ in relevant non-resource state, or an
active commitment reads a resource that differs between them, compare two sampled
continuations per eligible action. Unexpanded immediate randomness also uses this
bounded comparison when time remains.

Continue each comparison only to the remaining configured horizon, with the
existing immediate-value policy inside it. Never recursively launch further
policy comparisons. This values delayed payouts, promises, and changed encounters
that occur within the horizon. It adds at most two continuations per eligible
action per sensitive decision; runtime can grow quadratically with the horizon,
not exponentially with the number of future choices. Root progress continues to
count completed root samples, which now skip excluded actions.

Use paired seeds across actions. Extra policy sampling uses spawned RNGs and
does not consume the real rollout's future stream. It remains an approximation:
two inner samples can miss rare effects, greedy inner choices can miss strategies,
and consequences beyond the configured horizon remain outside the score.

## Alternatives

Evaluate work bounds and export a preference in the
[configurable policy comparison](planner-policy-options.html).

- Immediate policy everywhere is cheaper but rejects investments even when the
  configured horizon includes their return.
- Selective two-sample continuation is the bounded improvement selected here.
- Recursive lookahead is not selected because each extra decision multiplies work.
- Increasing the default horizon is deferred at the user's request; it is a
  separate runtime and product decision.

## Verification

Verify delayed rewards just inside and outside the remaining horizon, changed
encounters, no extra sampling for simple choices, and the exact nonrecursive work
bound. Keep the shared-RNG, adaptive, and rare-survival tests. Measure local timings
alongside the complete repository gate; do not claim unchanged runtime.
