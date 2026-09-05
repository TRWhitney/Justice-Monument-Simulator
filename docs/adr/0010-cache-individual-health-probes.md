# ADR 0010: Cache individual health probes

Status: accepted, 2026-09-05.

## Decision

Extend ADR 0007 with a bounded per-action cache beneath the projected Harbinger
risk cache. Evaluate misses through the existing reducer health probe, preserving
its `Rng(0)` estimate and action-preparation order. A blocked or unaffordable
action contributes no safe alternative, exactly as in the original risk loop.

Compile resource dependencies for deterministic outcomes and arrivals containing
only immediate resource operations and counter writes with case-only values.
Retain case, health, ended state, touched/payment resources, their floors, and
native action blocks. Dismissals additionally depend on their current balance
and the Harbinger dismissal block. Base Harbinger approval includes unpaid
penalty effects and coin affordability. Offer conditions remain the encounter
selector's responsibility; health probes have never evaluated those conditions.

Unknown effects, dynamic expressions or scaling, conditions, randomness, chains,
legacy all-resource affordability, requirements, matching triggers, and next-case
events bypass the narrow cache. Nonmatching contracts and events due later cannot
affect an immediate probe with these restricted effects. No general dependency
inference or state-key representation change is introduced.

Profiles retain their actual offer object, keyed by offer ID and action, so a
replacement definition bypasses them and pickling preserves valid references.
Each planner owns at most 10,000 probe entries; resetting planner caches resets
these entries too. Dataset definitions are treated as immutable during a planner
lifetime, as in the existing numeric and projected-risk caches.

## Alternatives

Compare and export the existing
[evaluation options](simulation-evaluation-options.html).

| Choice | Tradeoff |
| --- | --- |
| Restricted per-action reuse (selected) | Reuses probes across unrelated resource/history changes with a small proof boundary. |
| Whole projected-state cache only | Simpler, but invalidates all action checks together. |
| General effect dependency compiler | Could reuse more complex probes, but must model sequential writes, predicates, and trigger phases. Deferred. |

## Verification

Compare cached probes with full reductions across every builtin action, payment
and health boundaries, fractional values, floors, blocks, and active agreements.
Exercise custom formula/scaling/counter dependencies, due events, requirements,
random effects, bounded eviction, definition replacement, and worker pickling.
Compare seeded recommendation sample hashes against the archived pre-change code
and run the full repository gate.
