# ADR 0007: Reuse simulation evaluation work

Status: accepted, 2026-09-05.

## Decision

Keep ADRs 0001, 0003, 0005, and 0006's preparation, normalization, dead-end,
and bounded future-policy behavior. Optimize the work used to evaluate it:

- Prepare health probes through the reducer. For simple remaining outcomes that
  cannot affect health or end the run, omit final action bookkeeping. Matching
  action triggers, due events, randomness, and unpaid penalties use the shared
  completion function with the already prepared RNG.
- Cache projected client Harbinger risk separately from full utility. Preserve
  all state fields and contract payloads, order, and labels. Only counters absent
  from both data and saved-contract references can be omitted; the native
  Fizarre encounter counter is also retained. Cache instances belong to one
  planner/data lifetime and remain bounded.
- Cache numeric results by formula text and case only when AST name inspection
  proves the expressions and their scaling formulas have no resource, status,
  flag, or counter dependencies. Other formulas retain full context evaluation.
  Compilation and validation still use the existing expression interpreter.
- Reuse a chosen deterministic immediate transition. A single expanded random
  branch is insufficient: original random outcomes/ranges still consume the real
  rollout RNG. Construct an RNG's underlying generator on its first draw.
- Avoid state replacements that cannot change resource values or clear an
  already empty requirement. Preserve all intermediate rounding and floors.

The planner retains paired seeds, root sample counts, adaptive top-ups, and two
nonrecursive inner continuations. No smaller sampling budget masks runtime.

## Alternatives

Use the [configurable comparison](simulation-evaluation-options.html) to compare
evaluation approaches and horizon work bounds, then export a selection.

| Approach | Tradeoff |
| --- | --- |
| Shared reducer with proven shortcuts and bounded caches (selected) | Reuses existing semantics and has conservative complex-case fallbacks. |
| Full reductions for every score | Simple reference implementation, but repeats health-independent bookkeeping. |
| Separate mutable simulation engine | Could reduce allocations further, but duplicates transition semantics and requires a much larger equivalence effort. |

Cache dependencies include custom saved effects, not only builtin definitions.
The risk probe retains the existing deterministic `Rng(0)` scoring estimate;
it does not establish certain survival for random root actions.

## Verification

Compare the health probe against full actions across builtin offers, resource
boundaries, active agreements, and random preparation. Check custom formulas and
saved counter dependencies, bounded caches, RNG sequences and serialization, and
complete rollout states, samples, and draw counts with transition reuse disabled.
Run the repository gate and the seeded benchmark independently to avoid CPU
contention contaminating timings.
