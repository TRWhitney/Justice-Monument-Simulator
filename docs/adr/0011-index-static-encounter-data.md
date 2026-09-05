# ADR 0011: Index static encounter data

Status: accepted, 2026-09-05.

## Decision

Keep ADR 0002's ordered encounter distributions. Index ordinary candidates,
Harbinger and priority pools, NPC groups, and the client's fixed replacement-row
distributions once per dataset identity. Retain at most eight datasets in the
process-local cache. Indexes are rebuilt after process spawning and do not enter
the saved game format. Definitions are immutable for the lifetime of an index;
replacement datasets get separate indexes.

Build one predicate context lazily per eligibility scan and reuse it across
conditions. Never cache dynamic eligibility or model weights. Conditions still
read current resources, counters, flags, statuses, and pending labels. Custom
model implementations retain their existing `eligible_offers` method dispatch.

Preserve original offer order, duplicate pool entries, row multiplicity,
normalization order, override priority, and missing-pool fallbacks. Return copies
of cached row distributions so callers cannot corrupt later selection.

## Alternatives

Review and export the existing
[encounter options](client-case-options.html).

| Choice | Tradeoff |
| --- | --- |
| Static indexes and per-scan context (selected) | Removes repeated setup without invalidating learned or conditional behavior. |
| Cache final encounter distributions | Requires a complete dependency key for custom models and saved contracts. Deferred. |
| Rebuild every pool and context | Straightforward reference behavior with repeated scans and allocations. |

## Verification

Retain exact client distribution fixtures and seeded sample comparisons. Check
context reuse, changed state, mutable learned/weighted model inputs, custom
override targets, row multiplicity/order, independent returned maps, dataset
replacement, and bounded retention. Run the affected encounter tests and the
full repository gate.
