# ADR 0014: Own immutable contract payloads

Status: accepted, 2026-09-05.

## Decision

Copy JSON-like effect parameters, conditions, status data, probability formulas,
and encounter weight maps into owned immutable containers at model construction.
Mappings use a read-only backing map, nested sequences become tuples, and sets
become frozensets. Replacing a model reuses existing immutable children. Unknown
mutable leaf objects are rejected rather than silently entering a cached key.
Ordinary state counters, floors, and the outer status mapping remain live;
`GameState` itself does not memoize its complete key.

Cache canonical payload, effect, event, trigger, modifier, and override keys on
their owning immutable objects. Keys retain the same effect fields, labels,
conditions, list order, and map sorting as ADR 0013. Updated timers or effects
create new objects and therefore new keys. No global interning table retains
historical states or contracts.

Expression and display readers accept the mapping interface. Saved state and
benchmark exports recursively convert immutable children back to ordinary JSON
containers. Run-file versions and field shapes remain unchanged. Worker pickling
reconstructs backing maps without process identities; populated canonical keys
remain valid because their source payloads cannot change.

## Alternatives

Review and export the [evaluation options](simulation-evaluation-options.html).

| Choice | Tradeoff |
| --- | --- |
| Own immutable payloads and cache their keys (selected) | Prevents input aliasing and avoids repeated nested key construction, with some mapping read overhead. |
| Cache keys on shallowly frozen dataclasses | Smaller change, but mutable children could make the cached key stale. Rejected. |
| Keep rebuilding every key | Preserves mutable payloads but repeats canonicalization. |
| Make all game state deeply immutable | Broader API and reducer change than needed for reusable contract keys. Deferred. |

## Verification

Test mutation attempts, mutable input detachment, key reuse across resource-only
changes, key replacement after changed contracts, and dynamic counter keys.
Compare nested JSON and pickle round trips, snapshot formulas, end reasons, and
display fallbacks. Keep the complete numeric, reducer, persistence, planner, and
cache suites. Run the repository gate, the affected GUI interactions, and the
explicit artifact workflows into temporary directories. Compare seeded scores
and all samples against the pre-refactor archive; report net runtime separately
from the reduction in key-building work.
