# ADR 0021: Reuse exact Harbinger pool safety

Status: accepted, 2026-10-10.

The 32-sample, three-action, 20-case profile spends most of its time in projected
client Harbinger risk. ADR 0020 reuses individual payment probes, but repeatedly
selects and scans the same pool for balances with identical payment eligibility.

Cache pool membership and unsafe offer IDs across exact affordability and
eligibility regions. Derive payment cuts through the existing cost evaluator,
including the base unpaid check even when its declared payment resource differs.
Keep equality distinct from either side of every cut. Only direct resource to
literal comparisons admit resource regions. Counter to literal comparisons can
reuse their truth values; other counter expressions retain exact values.

Retain exact case, MH, ended state, MH floor, native action blocks and any flags,
statuses, pending labels or counters read by eligibility. Validate every possible
pool and Gratefulbinger definition with the existing restricted health proof.
Resource-changing arrivals, random outcomes, dynamic formulas, due events,
requirements, forced encounters and applicable custom overrides fall back to the
full evaluator. Matching contracts also fall back, except guards proved to read
only case index and false under the reducer predicate evaluator. This permits
Ghost's inactive Harbinger arrival without special-casing an agreement label.

Misses use the encounter selector and reducer probes. Recompute the live
Gratefulbinger replacement probability and retain the original ordered mix and
risk additions on every lookup. Factoring a summed probability would change
floating-point rounding. No approximate merging or policy pruning is allowed.
Caches belong to one immutable data lifetime and have bounded retention.

Broader dependency compilation would require a larger proof. Keeping only the
individual-probe cache leaves the demonstrated repeated pool work intact. See
[measurements and execution choices](../headless/latency.md).

Verification compares full reductions at payment and condition boundaries,
fractional balances, floors, blocks and contracts; exercises custom data fallback,
serialization and bounded retention; and compares complete seeded recommendations.
ADRs 0006 and 0016 still govern full-depth future policy evaluation.
