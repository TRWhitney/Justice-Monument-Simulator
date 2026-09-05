# ADR 0015: Reuse unchanged case collections

Status: accepted, 2026-09-05.

## Decision

During case advancement, retain the existing status mapping, encounter-modifier
tuple, and scheduled-event tuple until their first actual change. Allocate a
replacement status mapping only when a status ticks or expires. Allocate lists
for changed modifiers and due events only when such an entry is encountered.
Keep permanent records and unchanged event objects shared inside changed tuples.

This follows the existing reducer convention used by resource-only state
replacements: copy mappings before modifying them. The public outer status
mapping remains a mapping, and full state keys continue to read its current
contents. Only owned immutable contract payloads from ADR 0014 cache their keys.

Preserve starts-next-case timing, modifier expiration, duplicate entries, event
order, and the point at which due events are captured. Apply due effects after
status/modifier advancement with the original RNG; events newly created by an
effect are not retroactively added to that captured set.

## Alternatives

Review and export the [evaluation options](simulation-evaluation-options.html).

| Choice | Tradeoff |
| --- | --- |
| Copy on first change (selected) | Avoids allocations on ordinary advancement while keeping the same transitions. |
| Always rebuild all collections | Simpler loops but allocates for empty, permanent, and not-yet-due collections. |
| Dedicated mutable simulation state | Could remove more state replacements but requires a larger engine redesign. Deferred. |

## Verification

Verify object reuse for unchanged collections, unchanged prior states after
subsequent reducer operations, ticking/expiration, starts-next-case delays,
duplicate modifier/event ordering, random draws, and newly scheduled events.
Run the directly affected engine/planner tests and complete repository gate.
Compare full seeded recommendation samples against the pre-refactor archive.
