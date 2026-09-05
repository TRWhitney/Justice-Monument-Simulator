# ADR 0013: Name state comparison keys

Status: accepted, 2026-09-05.

## Decision

Introduce named `StateKey` and `ContractKey` tuples. The full state key keeps
every existing field, order, equality, and hash behavior from ADR 0007. Risk
evaluation builds the contract key once, discovers saved counter dependencies,
and passes that key into the full comparison with counters filtered before
sorting. No consumer extracts contracts or counters by positional slicing.

Expose non-resource comparison directly on `GameState`, preserving case,
flags, contracts, relevant counters, and terminal fields. The planner no longer
constructs a temporary replacement state just to zero its resource fields.
Keys remain in-memory implementation details; saved game formats do not change.

## Alternatives

Review and export the [evaluation options](simulation-evaluation-options.html).

| Choice | Tradeoff |
| --- | --- |
| Named tuple components (selected) | Makes dependencies explicit while preserving existing tuple comparisons. |
| Positional slices | Compact but silently depends on state field positions. |
| Wholesale state/contract object split | Could simplify sharing further, but would change many reducer and UI call sites. Deferred. |

## Verification

Check full-field coverage, a legacy tuple fixture, filtered and non-resource
comparison equivalence, and key pickling. Keep the saved consequence/order tests
and risk-cache dependency tests. Run directly affected unit tests and the full
repository gate before committing.
