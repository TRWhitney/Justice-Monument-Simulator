# ADR 0001: Reuse reducer preparation for action previews

Status: accepted, 2026-09-05.

## Context

Manual outcome prompts and state-dependent planner probabilities previously
used an earlier state than the reducer. Copying preparation into each caller
would allow encounter triggers, penalties, or dismissal costs to drift again.

## Decision

Extract the existing reducer preparation into `preview_state_before_outcome`.
The reducer and manual callers use the same sequence. Preview callers clone
the run RNG; the live action still applies every change exactly once.
The planner prepares state separately only for state-dependent probabilities,
avoiding duplicate work for ordinary deterministic and fixed-probability offers.

Keep the existing rollout planner and effect interpreter. Finite, fully resolved
outcomes support exact short-circuit scores. An unclassified eligible alternative
or unresolved random transition sends the decision through the existing rollout
path. A sampled death is insufficient evidence to hide the user's actions.

Shortcut refinement, 2026-09-05: matching pending contracts are not enough to
prove resource dominance. If a contract's predicate or formula reads a resource
that differs between the immediate outcomes, use rollouts. Fixed pending payouts
and predicates on resources that do not differ retain the shortcut. Existing
non-resource checks still reject changes to promises, counters, or encounter
state. Gratefulbinger and Poppy's ordinary gifts retain exact recommendations.

## Evaluated options

Use the [interactive option review](preview-options.html) to configure fallback
budgets, compare alternatives, and export a selection without changing the app.

| Option | Configuration and behavior | Decision |
| --- | --- | --- |
| Shared preparation plus exact shortcuts | Existing `horizon_cases`, `rollouts_per_action`, and adaptive settings continue to control fallback rollouts. Proven shortcuts require none. | Selected: consistent transitions and preserved immediate recommendations. |
| Always use rollouts | Increasing `rollouts_per_action` improves estimates but still cannot prove a rare survival chance is impossible. | Rejected: loses the existing short-circuit feature. |
| Separate manual and planner preparation | Each caller independently reproduces encounter, penalty, and dismissal handling. | Rejected: recreates the ordering defect and duplicated maintenance. |

## Consequences

The public state, persistence, RNG format, planner configuration, and UI rendering
architecture are unchanged. Exact scores have population outcome variance and
zero sampled observations; their mean has no Monte Carlo sampling uncertainty.
Unresolved random survival remains available conservatively until the action is
resolved, while deterministic terminal and blocked states retain their existing
game-over behavior.

See the [research and verification record](../simulation-audit-2026-09.md).
