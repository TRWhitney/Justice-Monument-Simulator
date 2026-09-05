# Simulation audit verification

Reviewed 2026-09-05. This change fixes the six engine, planner, and interface
consistency defects identified in the preceding audit. Builtin encounter data,
reward weights, suggested rules, and encounter-selection assumptions are unchanged.

## Game evidence

The official [web game](https://www.legendsofidleon.com/ytGl5oc/) loads
[N.js](https://www.legendsofidleon.com/ytGl5oc/N.js). The inspected response was
26,029,206 bytes, SHA-256
`079728c5ade09eff6496cccf503692b506ff8407641d72430d006baf239f2955`.
The live URL can change; no copy of the game bundle is committed here.

- `JusticeAccept` rounds scaled resource changes. The approval handler's
  `coincheck` compares the balance with the absolute value of that rounded
  result. Shark Attack at case 15 therefore requires 11 coins, not 11.25.
- The approval handler for encounter 54 applies a coin-flip Mental Health
  adjustment. `ScripticusApprovePromise` penalizes rejection and dismissal.
  A losing preview of the flip cannot establish that survival is impossible.
- `ScareLegal` reduces popularity before an ordinary encounter's decision.
  Manual outcome preparation must account for that arrival change.

The helper's [rounding function](https://github.com/rcoopr/idleon-justice/blob/main/src/lib/scaled-value.ts)
and [case multipliers](https://github.com/rcoopr/idleon-justice/blob/main/src/lib/hooks/use-case-mult.ts)
provide secondary corroboration. The wiki was unavailable to the research tools
(HTTP 403), so the official client supplied the primary evidence.

The official bundle also contains proportional Rupie exchanges and unequal
Billionaire reward branches that differ from the current model. Those are
separate data discrepancies, not prerequisites for fixing stale manual previews
or computing expectations from the configured distribution. They warrant a
dedicated data review against the supported game version; this patch does not
silently change the model's reward assumptions.

## Regression coverage

- Rounded payment boundaries in both debt modes, including the surviving
  Shark Attack approval and continued rejection of truly insufficient funds.
- A real Scripticus/Cool Bird sequence through the CLI and Qt choice dialog.
- Ghost/Rupie manual resolution agreeing with full simulation, without applying
  encounter triggers twice or consuming RNG draws during previews.
- Exact expected chests, utility, death probability, and variance for random
  guaranteed upside, with no rollouts.
- Probabilities evaluated after base effects, encounter triggers, required-action
  penalties, and dismissal costs, including random base effects.
- Unknown alternatives preventing an unsupported dominance shortcut, while
  state-dependent guaranteed upside still short-circuits.

Existing terminal-outcome, mixed-randomness, counter-dependency, affordability
exception, common-RNG-stream, and adaptive-sampling tests remain in place.

## Verification commands

Run `./scripts/validate_repo.sh` for the required complete gate. Direct affected
tests are in `tests/unit/test_simulation_regressions.py` and
`tests/gui/test_simulation_interactions.py`, alongside the existing reducer,
effects, planner, CLI, main-window controls, suggestion-panel, and progress tests.
There is no Playwright configuration or browser application in this repository;
the interaction paths are native Qt.

An explicit optional review-artifact workflow is:

```bash
JUSTICE_AUDIT_ARTIFACT_DIR=/tmp/justice-simulation-audit-review \
  uv run --with pytest pytest tests/gui/test_simulation_interactions.py -q
```

Ordinary test runs do not write these screenshots. Captures use synthetic states
and builtin offers and do not alter tracked review artifacts.
