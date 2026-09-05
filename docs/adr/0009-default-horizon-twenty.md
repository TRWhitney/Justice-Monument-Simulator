# ADR 0009: Plan twenty future cases by default

Status: accepted, 2026-09-05.

## Decision

Increase the builtin planner horizon from 12 to 20 future cases after the current
action. Keep 200 root rollouts per action, adaptive sampling up to 400, risk
weights, and ADR 0006's bounded future-policy comparisons. This supersedes that
ADR's earlier deferral of a default-horizon change.

Twenty cases include the builtin Honcho 15-Day Return's payout when considering
that investment now. Delayed opportunities encountered near the end of a rollout
can still mature outside its remaining horizon. A longer horizon is not a
guarantee of optimal decisions or complete coverage of every commitment.

## Configurable alternatives

The GUI Horizon control and CLI `planner set horizon <n>` retain user choice.
The [interactive comparison](simulation-evaluation-options.html) explains the
quadratic continuation work and exports a selection.

| Horizon | Use |
| --- | --- |
| 12 | Lower work, but the 15-case investment's full payout falls outside the root horizon. |
| 20 (selected) | Include the investment with more room for surrounding encounters. |
| 30 or 40 | Explore longer consequences at substantially higher evaluation cost. |

The builtin JSON is authoritative for application startup. Code/custom-data
fallbacks already use horizon 20; their separate sampling defaults remain intact.

## Verification

The default-horizon test follows the actual builtin investment through quiet
forced encounters, showing its payout absent at 12 and present at 20. Run the
repository gate and direct planner/GUI paths. Measure both horizons with the
same synthetic state and seed using `scripts/benchmark_planner.py`; horizon work
remains approximately quadratic despite faster evaluation.
