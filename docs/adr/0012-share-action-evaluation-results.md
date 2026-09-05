# ADR 0012: Share action evaluation results

Status: accepted, 2026-09-05.

## Decision

Compute immediate action outcomes once per recommendation decision and pass the
same results through eligibility, terminal detection, guaranteed-upside checks,
and exact scoring. Preserve the distinction between an unavailable action
(`[]`) and unresolved randomness (`None`). Results remain local to the current
decision; this adds no persistent transition cache.

After future-action eligibility and suggested constraints leave one action,
select it without utility calculation or comparison sampling. Root recommendations
still compute their configured rollout scores for a sole eligible action.
Retain ADR 0007's deterministic transition reuse guards: a single expanded
random branch still consumes the real rollout RNG when executed. ADR 0006's
two-continuation policy and horizon remain unchanged for competing actions.

## Alternatives

Review and export the existing
[policy options](planner-policy-options.html).

| Choice | Tradeoff |
| --- | --- |
| Local result sharing and sole-action shortcut (selected) | Removes redundant work without changing decision quality or root metrics. |
| Independent evaluation in each helper | Keeps helpers isolated but repeats reductions. |
| Persistent transition cache | Could reuse work across decisions but needs larger state and RNG keys. Deferred. |

## Verification

Assert one evaluation per action for terminal and guaranteed-upside root
shortcuts. Check sole-action and constrained-action selection without utility
calls, preserve random draw counts and realized arrival handling, and retain
root sampling, rare-survival, and adaptive-policy tests. Compare full seeded
recommendation sample hashes and run the repository gate.
