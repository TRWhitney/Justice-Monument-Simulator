# ADR 0023: Reuse exact predicate inputs

Status: accepted, 2026-10-10.

Whitney prioritizes lower CPU work because recommendations take long and make the
CPU hot. Optional workers remain available, with one process still the default.
The current profile identifies repeated eligibility predicates, probability
contexts, state copies and health-risk bookkeeping.

Use bounded caches owned by the existing immutable encounter dataset index for
regular eligibility and uniform proposal weights. Share predicate dependency
analysis with the Harbinger proof. Only direct, single comparisons with finite
numeric literals may reuse comparison truth values. Arithmetic, chained
comparisons and dynamic arguments retain exact referenced values and numeric
types. Counter access follows the existing float conversion. Flags, status names
and pending labels stay live. Syntax errors disable reuse so short-circuiting and
lazy errors remain the original evaluator's responsibility.

Always call the model's eligibility method. Cache proposal weights only for the
exact uniform model, and return independent lists/maps. Weighted, learned and
custom model weights, modifiers and ordered encounter replacements stay live.
Limit each eligibility/proposal cache to 256 variants; the existing eight-dataset
limit bounds data ownership.

Cache resource-only numeric probabilities by expression and exact typed resource
inputs, including zero signs, through the same safe expression evaluator. Scaling,
flags, statuses, counters and unsupported inputs retain full numeric contexts.
Bound profiles to 1024 expressions and values to 4096 entries. Reuse a risk sum
only for the identical immutable pool safety and live replacement probability.
Retain its original mix and addition order on misses; never factor probabilities.
Keep a strong safety reference with each result to prevent recycled identities.
Each risk cache remains bounded by the evaluator's configured maximum.

Extend the reducer's existing health-only probe to deterministic resource outcomes
when no chain, later trigger or due event can affect health. Apply effects in their
original order with the original prepared RNG and normalization. Actual action
reduction, resource results and action history remain unchanged.

For plain states, use positional constructor arguments only when stored field
order matches the dataclass definition and replacement names are valid. Reordered,
extended or subclass instances retain general replacement. ADR 0018's constructor
and shallow sharing requirements still apply.

Broader continuation/transition memoization was rejected after low hit rates.
Approximate state merging, reduced policy depth and extra CPU workers do not meet
this efficiency goal. The [execution comparison](planner-execution-options.html)
retains configurable worker and batch choices; [measurements](../headless/latency.md)
record CPU seconds separately from elapsed time.

Verify live custom predicates, numeric boundaries and types, collection isolation,
model dispatch, RNG draws, reducer equivalence, prepared roots, incremental
sampling, cancellation, installed-wheel loading and the complete repository gate.
