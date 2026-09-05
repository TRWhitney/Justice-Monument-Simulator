# ADR 0018: Copy plain states through their constructor

Status: accepted, 2026-09-05.

## Decision

Use `replace_state` for state replacements in effects, the reducer, encounter
consumption, risk projection, and simulated dead ends. For an exact `GameState`
instance whose stored attributes match its declared fields, merge its attribute
mapping with the requested changes and call the normal constructor. This avoids
repeated dataclass field reflection while preserving all field values and shallow
collection sharing. It does not bypass initialization or mutate the source.

Subclasses and instances with additional or missing attributes use
`dataclasses.replace`. Extra derived attributes must not enter the constructor or
be copied as cached state. Field names are derived from the dataclass definition.
Unknown replacement names continue to fail through constructor validation.
Other dataclass records retain their existing replacement path.

## Alternatives

Review the [evaluation options](simulation-evaluation-options.html).

| Choice | Consequence |
| --- | --- |
| Specialized plain-state copying (selected) | Reduces reflection while retaining constructor semantics and existing reducer ordering. |
| General dataclass replacement everywhere | Simpler call surface, with repeated reflection in the hottest state transitions. |
| Bypass constructors or mutate simulation states | Requires a larger correctness boundary; not selected. |

This optimization changes no probabilities, policy, budgets, horizon, RNG draws,
rounding, or transition ordering. Equivalence comparisons use the same policy on
both sides; ADRs 0016 and 0017 intentionally change recommendations separately.

## Verification

Compare every builtin action under three states against general replacement,
including labels, complete resulting states, failures, and RNG draw counts.
Exercise every field, shared collections, subclass initialization, extra
attributes, invalid fields, and pickle round trips. Compare complete seeded
recommendation hashes, including utility samples, with the helper disabled.
Run affected engine/planner/persistence tests and the complete repository gate.

## Measured results

Python 3.12.3, Kitchen Loan root offer, seed 42, five samples per action,
adaptive sampling disabled. Both sides include ADR 0016's probability integration.
The reference replaces imported `replace_state` helpers with `dataclasses.replace`;
all other code and configuration are identical. Timers cover recommendation work.

| State | Horizon | General copy | Specialized copy |
| --- | ---: | ---: | ---: |
| Baseline | 20 | 2.300 s | 2.141 s |
| Baseline | 40 | 8.806 s | 8.300 s |
| Active loan | 40 | 10.631 s | 9.911 s |
| Due event | 40 | 7.987 s | 7.439 s |
| Low health | 20 | 1.236 s | 1.151 s |
| Encounter override | 20 | 1.970 s | 1.837 s |

All six complete recommendation hashes, including every utility sample, matched.
An additional baseline check at horizon 20, seed 77, and 25 samples per action
also matched exactly: 8.768 s with general copying and 8.228 s with specialization.
These small local probes indicate a roughly 6–7% reduction from copying alone;
they do not measure a net speedup over the former policy or establish general
recommendation accuracy. Probability integration and additional contenders can
increase total runtime. The full gate passed 389 unit tests, 69 GUI tests,
formatting, linting, schemas, and smoke launch; 78 directly affected tests passed.
