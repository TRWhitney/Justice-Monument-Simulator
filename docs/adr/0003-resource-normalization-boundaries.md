# ADR 0003: Normalize client resources after actions

Status: accepted, 2026-09-05.

## Decision

The builtin dataset opts into `special_rules.normalize_after_action`. Effects
still round whole resources, but defer implicit zero clamps and permanent floors
until the complete action resolves, before advancing to the next case. Explicit
clamp effects continue to apply at their specified position.

Reuse the existing reducer preparation for affordability, CLI/Qt manual choices,
and planner evaluation. An arrival can temporarily leave popularity negative or
below Never Uncool's floor; action formulas must see that value. Final normalization
also clamps mental health in `clamp_to_zero` mode. This corrects Gratefulbinger's
recorded death state without changing the death threshold.

The client's Ghost drain is an explicit exception: apply it before NPC-specific
arrival triggers and clamp its result to zero without applying the permanent
floor. Identify it through the existing `ghost_scare_pop` label under
`client_encounters`, so saved agreement payloads keep working without migration.
Other custom triggers retain their order.

## Configurable alternatives

| Configuration | Behavior | Use |
| --- | --- | --- |
| `normalize_after_action: true`, `debt_mode: clamp_to_zero` | Preserve intermediate values, then clamp all main resources and restore floors after the action. | Builtin client behavior. |
| `normalize_after_action: false` | Preserve the original per-effect clamps and floors; MH can remain negative. | Default for existing custom datasets. |
| `normalize_after_action: true`, `debt_mode: allow_negative` | Preserve debt after the action; restore explicit permanent floors. | Explicit custom debt behavior. |

Unconditionally changing all datasets would alter existing custom contracts.
Clamping only at arrival completion would still erase Hand's temporary debt and
would let Never Uncool make a blocked approval affordable. Neither is suitable.

## Verification

Client-derived boundary tests cover Hand, both Ghost/Hand agreement orders,
Never Uncool payment gates and Rupie formulas, Gratefulbinger health and utility,
manual resolution, and custom/debt compatibility. Exact Billionaire expectations
still bypass rollouts with the popularity floor active. Direct Qt tests exercise
the corrected controls and resulting states.
